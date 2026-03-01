import requests

from .deps import HandlerDeps


def generate_page(*, deps: HandlerDeps, request_obj, flash_fn, redirect_fn, url_for_fn, render_template_fn):
    available_topics = deps.get_existing_topics_fn()
    if request_obj.method == "POST":
        selected_topic = request_obj.form.get("topic_select", "").strip()
        custom_topic = request_obj.form.get("topic_new", "").strip()
        topic_legacy = request_obj.form.get("topic", "").strip()
        topic = custom_topic or selected_topic or topic_legacy
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
            inserted, duplicates = deps.add_questions_fn(
                topic,
                count,
                language=language,
                additional_context=additional_context or None,
                topic_color=resolved_topic_color,
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
        topic_tag_colors=deps.topic_tag_colors,
    )
