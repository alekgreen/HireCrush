import requests

from interview_app.utils import parse_topic_subtopic, serialize_topic_subtopic

from .deps import GenerationHandlerDeps


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
        selected_topic = request_obj.form.get("topic_select", "").strip()
        custom_topic = request_obj.form.get("topic_new", "").strip()
        topic_legacy = request_obj.form.get("topic", "").strip()
        topic = custom_topic or selected_topic or topic_legacy
        selected_subtopic_raw = request_obj.form.get("subtopic_select", "").strip()
        custom_subtopic = request_obj.form.get("subtopic_new", "").strip()
        subtopic = custom_subtopic or ""
        selected_subtopic_pair = (
            parse_topic_subtopic(selected_subtopic_raw) if selected_subtopic_raw else None
        )
        if selected_subtopic_raw and selected_subtopic_pair is None:
            flash_fn("Subtopic selection is invalid.", "error")
            return redirect_fn(url_for_fn("generate"))
        if selected_subtopic_pair is not None and not topic:
            topic = selected_subtopic_pair[0]
        if selected_subtopic_pair is not None and topic.lower() != selected_subtopic_pair[0].lower():
            flash_fn("Selected subtopic does not belong to the chosen topic.", "error")
            return redirect_fn(url_for_fn("generate"))
        if selected_subtopic_pair is not None and not subtopic:
            subtopic = selected_subtopic_pair[1]

        additional_context = request_obj.form.get("additional_context", "").strip()
        topic_color_raw = request_obj.form.get("topic_color", "").strip().lower()
        count_raw = request_obj.form.get("count", "5").strip()
        language_code = request_obj.form.get(
            "language", deps.default_generation_language_code
        ).strip().lower()
        language = deps.generation_language_by_code.get(language_code)

        if not topic:
            flash_fn("Topic is required.", "error")
            return redirect_fn(url_for_fn("generate"))
        if subtopic and not topic:
            flash_fn("Topic is required when using a subtopic.", "error")
            return redirect_fn(url_for_fn("generate"))
        if language is None:
            flash_fn("Language is invalid.", "error")
            return redirect_fn(url_for_fn("generate"))
        if topic_color_raw and topic_color_raw not in deps.topic_tag_color_by_code:
            flash_fn("Topic tag color is invalid.", "error")
            return redirect_fn(url_for_fn("generate"))

        resolved_topic_color = (
            topic_color_raw
            or deps.get_recent_topic_color_fn(topic)
            or deps.default_topic_tag_color_code
        )

        try:
            count = max(1, min(20, int(count_raw)))
        except ValueError:
            flash_fn("Count must be an integer.", "error")
            return redirect_fn(url_for_fn("generate"))

        try:
            add_kwargs = {
                "language": language,
                "additional_context": additional_context or None,
                "topic_color": resolved_topic_color,
            }
            if subtopic:
                add_kwargs["subtopic"] = subtopic
            try:
                inserted, duplicates = deps.add_questions_fn(
                    topic,
                    count,
                    **add_kwargs,
                )
            except TypeError:
                add_kwargs.pop("subtopic", None)
                inserted, duplicates = deps.add_questions_fn(
                    topic,
                    count,
                    **add_kwargs,
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
    )
