import json

import requests

from .deps import ReviewHandlerDeps


def _build_selected_subtopic_filters(
    *,
    deps: ReviewHandlerDeps,
    selected_subtopics: list[tuple[str, str]],
) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []
    for topic, subtopic in selected_subtopics:
        value = deps.serialize_topic_subtopic_filter_fn(topic, subtopic)
        if not value:
            continue
        filters.append(
            {
                "topic": topic,
                "subtopic": subtopic,
                "value": value,
                "label": f"{topic} / {subtopic}",
            }
        )
    return filters


def review_page(*, deps: ReviewHandlerDeps, request_obj, render_template_fn):
    selected_topics = deps.normalize_topic_filters_fn(request_obj.args.getlist("topics"))
    selected_subtopics = deps.normalize_subtopic_filters_fn(request_obj.args.getlist("subtopics"))
    randomize = deps.is_randomized_review_fn(request_obj.args.get("randomize", ""))
    skipped_qid = request_obj.args.get("skip_qid", type=int)
    requested_qid = request_obj.args.get("qid", type=int)
    show_feedback = str(request_obj.args.get("show_feedback", "")).strip().lower() in {
        "1",
        "true",
        "yes",
    }

    question = deps.get_question_by_id_fn(requested_qid) if requested_qid else None
    if question is None:
        try:
            question = deps.get_due_question_fn(
                topics=selected_topics,
                subtopics=selected_subtopics,
                randomize=randomize,
                exclude_question_id=skipped_qid,
            )
        except TypeError:
            question = deps.get_due_question_fn(
                topics=selected_topics,
                randomize=randomize,
                exclude_question_id=skipped_qid,
            )
        if question is None and skipped_qid is not None:
            try:
                question = deps.get_due_question_fn(
                    topics=selected_topics,
                    subtopics=selected_subtopics,
                    randomize=randomize,
                )
            except TypeError:
                question = deps.get_due_question_fn(
                    topics=selected_topics,
                    randomize=randomize,
                )

    stats = deps.get_stats_fn()
    upcoming = None
    latest_feedback = None
    review_reappearance_labels: dict[str, str] = {}
    if question is None:
        try:
            upcoming = deps.get_next_upcoming_fn(topics=selected_topics, subtopics=selected_subtopics)
        except TypeError:
            upcoming = deps.get_next_upcoming_fn(topics=selected_topics)
    else:
        review_reappearance_labels = deps.get_review_reappearance_labels_fn(question)
        if show_feedback:
            latest_feedback = deps.get_latest_feedback_fn(question["id"])

    return render_template_fn(
        "review.html",
        question=question,
        stats=stats,
        upcoming=upcoming,
        latest_feedback=latest_feedback,
        review_reappearance_labels=review_reappearance_labels,
        selected_topics=selected_topics,
        selected_subtopics=_build_selected_subtopic_filters(
            deps=deps,
            selected_subtopics=selected_subtopics,
        ),
        randomize=randomize,
    )


def _resolve_review_filters_from_form(
    *,
    deps: ReviewHandlerDeps,
    request_obj,
) -> tuple[list[str], list[tuple[str, str]], bool]:
    selected_topics = deps.normalize_topic_filters_fn(request_obj.form.getlist("topics"))
    selected_subtopics = deps.normalize_subtopic_filters_fn(request_obj.form.getlist("subtopics"))
    randomize = deps.is_randomized_review_fn(request_obj.form.get("randomize", ""))
    if not selected_topics and not selected_subtopics and not randomize:
        extracted = deps.extract_review_filters_from_referrer_fn()
        if len(extracted) == 3:
            selected_topics, selected_subtopics, randomize = extracted
        else:
            selected_topics, randomize = extracted
            selected_subtopics = []
    return selected_topics, selected_subtopics, randomize


def review_submit_action(
    *,
    deps: ReviewHandlerDeps,
    question_id: int,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    rating_map = {"again": 2, "hard": 3, "good": 4, "easy": 5}
    grade = request_obj.form.get("grade", "").strip().lower()
    rating = rating_map.get(grade)
    if rating is None:
        flash_fn("Invalid review grade.", "error")
        return redirect_fn(url_for_fn("review"))

    deps.apply_review_fn(question_id, rating)
    selected_topics, selected_subtopics, randomize = _resolve_review_filters_from_form(
        deps=deps,
        request_obj=request_obj,
    )
    return deps.review_redirect_fn(
        topics=selected_topics,
        subtopics=selected_subtopics,
        randomize=randomize,
    )


def review_skip_action(*, deps: ReviewHandlerDeps, question_id: int, request_obj):
    selected_topics, selected_subtopics, randomize = _resolve_review_filters_from_form(
        deps=deps,
        request_obj=request_obj,
    )
    return deps.review_redirect_fn(
        topics=selected_topics,
        subtopics=selected_subtopics,
        randomize=randomize,
        skip_qid=question_id,
    )


def review_answer_action(
    *,
    deps: ReviewHandlerDeps,
    question_id: int,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    question = deps.get_question_by_id_fn(question_id)
    if question is None:
        flash_fn("Question not found.", "error")
        return redirect_fn(url_for_fn("review"))

    try:
        deps.generate_answer_for_question_fn(question_id)
        flash_fn("Model answer is ready.", "success")
    except requests.HTTPError as exc:
        flash_fn(deps.format_http_error_fn(exc), "error")
    except Exception as exc:
        flash_fn(f"Could not generate answer: {exc}", "error")

    selected_topics, selected_subtopics, randomize = _resolve_review_filters_from_form(
        deps=deps,
        request_obj=request_obj,
    )
    return deps.review_redirect_fn(
        topics=selected_topics,
        subtopics=selected_subtopics,
        randomize=randomize,
        qid=question_id,
    )


def review_answer_stream_action(
    *,
    deps: ReviewHandlerDeps,
    question_id: int,
    response_class,
    stream_with_context_fn,
):
    question = deps.get_question_by_id_fn(question_id)
    if question is None:
        payload = {"type": "error", "message": "Question not found."}
        return response_class(
            json.dumps(payload) + "\n",
            status=404,
            mimetype="application/x-ndjson",
        )

    def generate():
        try:
            for piece in deps.stream_answer_for_question_fn(question_id):
                if piece:
                    yield json.dumps({"type": "chunk", "text": piece}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
        except requests.HTTPError as exc:
            yield json.dumps({"type": "error", "message": deps.format_http_error_fn(exc)}) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": f"Could not generate answer: {exc}"}) + "\n"

    return response_class(
        stream_with_context_fn(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def review_feedback_action(
    *,
    deps: ReviewHandlerDeps,
    question_id: int,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    question = deps.get_question_by_id_fn(question_id)
    if question is None:
        flash_fn("Question not found.", "error")
        return redirect_fn(url_for_fn("review"))

    user_answer = request_obj.form.get("user_answer", "").strip()
    selected_topics, selected_subtopics, randomize = _resolve_review_filters_from_form(
        deps=deps,
        request_obj=request_obj,
    )

    question_type = (question["question_type"] or "theory") if "question_type" in question.keys() else "theory"
    min_answer_length = 5 if question_type == "code_review" else 20
    if len(user_answer) < min_answer_length:
        flash_fn("Please enter a longer answer to get meaningful feedback.", "error")
        return deps.review_redirect_fn(
            topics=selected_topics,
            subtopics=selected_subtopics,
            randomize=randomize,
            qid=question_id,
        )

    show_feedback = False
    try:
        if question_type == "code_review":
            original_code = (question["code_snippet"] or "") if "code_snippet" in question.keys() else ""
            code_language = (question["code_language"] or "") if "code_language" in question.keys() else ""
            result = deps.call_gemini_for_code_review_feedback_fn(
                question_text=question["text"],
                original_code=original_code,
                user_code=user_answer,
                language=code_language,
            )
        else:
            reference_answer = deps.generate_answer_for_question_fn(question_id)
            result = deps.call_gemini_for_feedback_fn(
                question=question["text"],
                reference_answer=reference_answer,
                user_answer=user_answer,
            )
        deps.save_feedback_fn(question_id, user_answer, result)
        show_feedback = True
        flash_fn("Feedback generated.", "success")
    except requests.HTTPError as exc:
        flash_fn(deps.format_http_error_fn(exc), "error")
    except Exception as exc:
        flash_fn(f"Could not evaluate answer: {exc}", "error")

    if show_feedback:
        return deps.review_redirect_fn(
            topics=selected_topics,
            subtopics=selected_subtopics,
            randomize=randomize,
            qid=question_id,
            show_feedback=True,
        )
    return deps.review_redirect_fn(
        topics=selected_topics,
        subtopics=selected_subtopics,
        randomize=randomize,
        qid=question_id,
    )


def review_transcribe_action(*, deps: ReviewHandlerDeps, request_obj, jsonify_fn):
    audio_file = request_obj.files.get("audio")
    if audio_file is None:
        return jsonify_fn({"error": "Audio file is required."}), 400

    mime_type = deps.normalize_audio_mime_type_fn(audio_file.mimetype or "")
    if mime_type is None:
        return (
            jsonify_fn(
                {
                    "error": (
                        "Unsupported audio format. Use MP3, M4A/MP4, WEBM, WAV, AIFF, AAC, OGG, or FLAC."
                    )
                }
            ),
            400,
        )

    audio_bytes = audio_file.read()
    if not audio_bytes:
        return jsonify_fn({"error": "Audio file is empty."}), 400
    if len(audio_bytes) > deps.max_inline_audio_bytes:
        return jsonify_fn({"error": "Audio file is too large. Keep uploads under 19 MB."}), 400

    try:
        transcript = deps.call_gemini_for_transcription_fn(audio_bytes, mime_type)
        return jsonify_fn({"transcript": transcript}), 200
    except requests.HTTPError as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 502)
        if status == 429:
            return jsonify_fn({"error": deps.format_http_error_fn(exc)}), 429
        if status in {400, 413, 415}:
            return jsonify_fn({"error": "Gemini could not process this audio file."}), 400
        if status == 404:
            return jsonify_fn({"error": deps.format_http_error_fn(exc)}), 500
        return jsonify_fn({"error": deps.format_http_error_fn(exc)}), 502
    except Exception as exc:
        return jsonify_fn({"error": f"Transcription failed: {exc}"}), 500
