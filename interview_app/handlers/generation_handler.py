import threading
import time
import uuid

import requests

from interview_app.utils import parse_topic_subtopic, serialize_topic_subtopic

from .deps import GenerationHandlerDeps

_GENERATION_JOBS: dict[str, dict] = {}
_GENERATION_JOBS_LOCK = threading.Lock()
_GENERATION_JOB_TTL_SECONDS = 15 * 60
_GENERATION_MAX_TRACKED_JOBS = 300


def _build_available_subtopics(topic_subtopic_rows) -> list[dict]:
    options: list[dict] = []
    seen: set[str] = set()
    for row in topic_subtopic_rows:
        topic = str(row["topic"]).strip()
        subtopic = str(row["subtopic"]).strip()
        value = serialize_topic_subtopic(topic, subtopic)
        if not value or value in seen:
            continue
        seen.add(value)
        options.append(
            {
                "topic": topic,
                "subtopic": subtopic,
                "value": value,
                "label": f"{topic} / {subtopic}",
            }
        )
    options.sort(key=lambda item: (item["topic"].lower(), item["subtopic"].lower()))
    return options


def _parse_generation_request(*, deps: GenerationHandlerDeps, request_obj) -> tuple[dict | None, str | None]:
    selected_topic = request_obj.form.get("topic_select", "").strip()
    custom_topic = request_obj.form.get("topic_new", "").strip()
    topic_legacy = request_obj.form.get("topic", "").strip()
    topic = custom_topic or selected_topic or topic_legacy
    selected_subtopic_raw = request_obj.form.get("subtopic_select", "").strip()
    custom_subtopic = request_obj.form.get("subtopic_new", "").strip()
    subtopic = custom_subtopic or ""
    selected_subtopic_pair = parse_topic_subtopic(selected_subtopic_raw) if selected_subtopic_raw else None

    if selected_subtopic_raw and selected_subtopic_pair is None:
        return None, "Subtopic selection is invalid."
    if selected_subtopic_pair is not None and not topic:
        topic = selected_subtopic_pair[0]
    if selected_subtopic_pair is not None and topic.lower() != selected_subtopic_pair[0].lower():
        return None, "Selected subtopic does not belong to the chosen topic."
    if selected_subtopic_pair is not None and not subtopic:
        subtopic = selected_subtopic_pair[1]

    additional_context = request_obj.form.get("additional_context", "").strip()
    topic_color_raw = request_obj.form.get("topic_color", "").strip().lower()
    count_raw = request_obj.form.get("count", "5").strip()
    language_code = request_obj.form.get("language", deps.default_generation_language_code).strip().lower()
    language = deps.generation_language_by_code.get(language_code)
    question_type = request_obj.form.get("question_type", "theory").strip().lower()

    if not topic:
        return None, "Topic is required."
    if subtopic and not topic:
        return None, "Topic is required when using a subtopic."
    if language is None:
        return None, "Language is invalid."
    if topic_color_raw and topic_color_raw not in deps.topic_tag_color_by_code:
        return None, "Topic tag color is invalid."

    valid_question_types = {code for code, _ in deps.question_types}
    if question_type not in valid_question_types:
        question_type = "theory"

    resolved_topic_color = (
        topic_color_raw
        or deps.get_recent_topic_color_fn(topic)
        or deps.default_topic_tag_color_code
    )
    try:
        count = max(1, min(20, int(count_raw)))
    except ValueError:
        return None, "Count must be an integer."

    add_kwargs = {
        "language": language,
        "additional_context": additional_context or None,
        "topic_color": resolved_topic_color,
    }
    if subtopic:
        add_kwargs["subtopic"] = subtopic

    return {
        "topic": topic,
        "count": count,
        "question_type": question_type,
        "add_kwargs": add_kwargs,
    }, None


def _invoke_add_fn(add_fn, topic: str, count: int, add_kwargs: dict) -> tuple[int, int]:
    candidates: list[dict] = [dict(add_kwargs)]
    if "subtopic" in add_kwargs:
        kwargs_no_subtopic = dict(add_kwargs)
        kwargs_no_subtopic.pop("subtopic", None)
        candidates.append(kwargs_no_subtopic)
    if "progress_callback" in add_kwargs:
        kwargs_no_progress = dict(add_kwargs)
        kwargs_no_progress.pop("progress_callback", None)
        candidates.append(kwargs_no_progress)
    if "subtopic" in add_kwargs and "progress_callback" in add_kwargs:
        kwargs_minimal = dict(add_kwargs)
        kwargs_minimal.pop("subtopic", None)
        kwargs_minimal.pop("progress_callback", None)
        candidates.append(kwargs_minimal)

    tried: set[tuple[str, ...]] = set()
    last_error = None
    for kwargs in candidates:
        key = tuple(sorted(kwargs.keys()))
        if key in tried:
            continue
        tried.add(key)
        try:
            return add_fn(topic, count, **kwargs)
        except TypeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError("Could not invoke generation function.")


def _execute_generation(
    *,
    deps: GenerationHandlerDeps,
    payload: dict,
    progress_callback=None,
) -> tuple[int, int]:
    if payload["question_type"] == "code_review":
        add_fn = deps.add_code_review_questions_fn
    else:
        add_fn = deps.add_questions_fn

    call_kwargs = dict(payload["add_kwargs"])
    if progress_callback is not None:
        call_kwargs["progress_callback"] = progress_callback
    return _invoke_add_fn(add_fn, payload["topic"], payload["count"], call_kwargs)


def _prune_generation_jobs_locked(now_ts: float) -> None:
    expired_job_ids = [
        job_id
        for job_id, job in _GENERATION_JOBS.items()
        if job["status"] in {"completed", "failed"}
        and (now_ts - float(job.get("updated_at", now_ts))) > _GENERATION_JOB_TTL_SECONDS
    ]
    for job_id in expired_job_ids:
        _GENERATION_JOBS.pop(job_id, None)

    overflow = len(_GENERATION_JOBS) - _GENERATION_MAX_TRACKED_JOBS
    if overflow <= 0:
        return

    removable = sorted(
        (
            (job_id, float(job.get("updated_at", now_ts)))
            for job_id, job in _GENERATION_JOBS.items()
            if job["status"] != "running"
        ),
        key=lambda item: item[1],
    )
    for job_id, _updated_at in removable[:overflow]:
        _GENERATION_JOBS.pop(job_id, None)


def _create_generation_job(*, requested_count: int, question_type: str) -> str:
    job_id = uuid.uuid4().hex
    now_ts = time.time()
    with _GENERATION_JOBS_LOCK:
        _prune_generation_jobs_locked(now_ts)
        _GENERATION_JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "requested_count": requested_count,
            "inserted": 0,
            "remaining": requested_count,
            "question_type": question_type,
            "error": None,
            "created_at": now_ts,
            "updated_at": now_ts,
        }
    return job_id


def _set_generation_job_progress(job_id: str, inserted: int, requested_count: int) -> None:
    now_ts = time.time()
    with _GENERATION_JOBS_LOCK:
        job = _GENERATION_JOBS.get(job_id)
        if job is None:
            return
        safe_total = max(1, int(requested_count))
        safe_inserted = max(0, min(int(inserted), safe_total))
        job["requested_count"] = safe_total
        job["inserted"] = safe_inserted
        job["remaining"] = max(0, safe_total - safe_inserted)
        job["updated_at"] = now_ts


def _set_generation_job_status(job_id: str, status: str, **updates) -> None:
    now_ts = time.time()
    with _GENERATION_JOBS_LOCK:
        job = _GENERATION_JOBS.get(job_id)
        if job is None:
            return
        job["status"] = status
        job["updated_at"] = now_ts
        job.update(updates)


def _get_generation_job(job_id: str) -> dict | None:
    with _GENERATION_JOBS_LOCK:
        job = _GENERATION_JOBS.get(job_id)
        if job is None:
            return None
        return dict(job)


def _run_generation_job(
    *,
    app_obj,
    deps: GenerationHandlerDeps,
    payload: dict,
    job_id: str,
) -> None:
    def progress_callback(inserted: int, requested_count: int) -> None:
        _set_generation_job_progress(job_id, inserted, requested_count)

    _set_generation_job_status(job_id, "running")
    try:
        with app_obj.app_context():
            inserted, remaining = _execute_generation(
                deps=deps,
                payload=payload,
                progress_callback=progress_callback,
            )
        _set_generation_job_progress(job_id, inserted, payload["count"])
        _set_generation_job_status(
            job_id,
            "completed",
            inserted=inserted,
            remaining=remaining,
        )
    except requests.HTTPError as exc:
        _set_generation_job_status(
            job_id,
            "failed",
            error=deps.format_http_error_fn(exc),
        )
    except Exception as exc:
        _set_generation_job_status(
            job_id,
            "failed",
            error=f"Generation failed: {exc}",
        )


def generate_start(
    *,
    deps: GenerationHandlerDeps,
    request_obj,
    jsonify_fn,
    app_obj,
):
    payload, error = _parse_generation_request(deps=deps, request_obj=request_obj)
    if error:
        return jsonify_fn({"ok": False, "error": error}), 400

    job_id = _create_generation_job(
        requested_count=payload["count"],
        question_type=payload["question_type"],
    )
    worker = threading.Thread(
        target=_run_generation_job,
        kwargs={
            "app_obj": app_obj,
            "deps": deps,
            "payload": payload,
            "job_id": job_id,
        },
        daemon=True,
    )
    worker.start()
    return (
        jsonify_fn(
            {
                "ok": True,
                "job_id": job_id,
                "requested_count": payload["count"],
                "question_type": payload["question_type"],
            }
        ),
        202,
    )


def generate_progress(
    *,
    job_id: str,
    jsonify_fn,
):
    job = _get_generation_job(job_id)
    if job is None:
        return jsonify_fn({"ok": False, "error": "Generation job not found."}), 404
    return jsonify_fn(
        {
            "ok": True,
            "job_id": job["job_id"],
            "status": job["status"],
            "inserted": int(job.get("inserted", 0)),
            "requested_count": int(job.get("requested_count", 0)),
            "remaining": int(job.get("remaining", 0)),
            "question_type": job.get("question_type", "theory"),
            "error": job.get("error"),
        }
    )


def generate_page(
    *,
    deps: GenerationHandlerDeps,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
    render_template_fn,
):
    available_topics = deps.get_existing_topics_fn()
    available_subtopics = _build_available_subtopics(deps.list_topic_subtopics_fn(limit=500))
    if request_obj.method == "POST":
        payload, error = _parse_generation_request(deps=deps, request_obj=request_obj)
        if error:
            flash_fn(error, "error")
            return redirect_fn(url_for_fn("generate"))

        try:
            inserted, duplicates = _execute_generation(
                deps=deps,
                payload=payload,
            )
        except requests.HTTPError as exc:
            flash_fn(deps.format_http_error_fn(exc), "error")
            return redirect_fn(url_for_fn("generate"))
        except Exception as exc:
            flash_fn(f"Generation failed: {exc}", "error")
            return redirect_fn(url_for_fn("generate"))

        if inserted:
            flash_fn(f"Added {inserted} unique question(s).", "success")
        if duplicates:
            flash_fn(
                f"Could not add {duplicates} question(s) after uniqueness checks.",
                "info",
            )
        return redirect_fn(url_for_fn("index"))

    return render_template_fn(
        "generate.html",
        generation_languages=deps.generation_languages,
        selected_language=deps.default_generation_language_code,
        available_topics=available_topics,
        available_subtopics=available_subtopics,
        topic_tag_colors=deps.topic_tag_colors,
        question_types=deps.question_types,
        generation_start_url=url_for_fn("generate_start"),
        generation_progress_url_template=url_for_fn("generate_progress", job_id="__JOB_ID__"),
    )
