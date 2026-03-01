import sqlite3

from .deps import CatalogHandlerDeps


def _build_topic_subtopics(subtopic_rows) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for row in subtopic_rows:
        topic = str(row["topic"]).strip()
        if not topic:
            continue
        grouped.setdefault(topic, []).append(row)
    return grouped


def questions_page(*, deps: CatalogHandlerDeps, render_template_fn):
    rows = deps.list_questions_fn(limit=200)
    return render_template_fn("questions.html", questions=rows)


def topics_page(*, deps: CatalogHandlerDeps, request_obj, render_template_fn):
    selected_topic = request_obj.args.get("topic", "").strip()
    selected_subtopic = request_obj.args.get("subtopic", "").strip()
    if selected_topic:
        if selected_subtopic:
            rows = deps.list_questions_by_subtopic_fn(selected_topic, selected_subtopic, limit=400)
        else:
            rows = deps.list_questions_by_topic_fn(selected_topic, limit=400)
        subtopic_rows = deps.list_subtopics_with_stats_fn(topic=selected_topic, limit=400)
        return render_template_fn(
            "topics.html",
            selected_topic=selected_topic,
            selected_subtopic=selected_subtopic,
            topic_questions=rows,
            topic_subtopics=_build_topic_subtopics(subtopic_rows),
        )

    rows = deps.list_topics_with_stats_fn(limit=200)
    subtopic_rows = deps.list_subtopics_with_stats_fn(limit=500)
    return render_template_fn(
        "topics.html",
        topics=rows,
        selected_topic="",
        selected_subtopic="",
        topic_questions=[],
        topic_subtopics=_build_topic_subtopics(subtopic_rows),
    )


def _form_text(request_obj, field_name: str) -> str:
    return str(request_obj.form.get(field_name, "")).strip()


def _resolve_next_path(*, request_obj, url_for_fn, fallback_endpoint: str) -> str:
    next_path = _form_text(request_obj, "next")
    if next_path.startswith("/"):
        return next_path
    return url_for_fn(fallback_endpoint)


def question_update_action(
    *,
    deps: CatalogHandlerDeps,
    question_id: int,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    question_text = request_obj.form.get("text", "")
    topic = _form_text(request_obj, "topic")
    subtopic = _form_text(request_obj, "subtopic")
    redirect_path = _resolve_next_path(
        request_obj=request_obj,
        url_for_fn=url_for_fn,
        fallback_endpoint="questions",
    )

    if subtopic and not topic:
        flash_fn("Topic is required when subtopic is set.", "error")
        return redirect_fn(redirect_path)

    try:
        updated = deps.update_question_fn(
            question_id,
            text=question_text,
            topic=topic or None,
            subtopic=subtopic or None,
        )
    except sqlite3.IntegrityError:
        flash_fn("A question with the same text already exists.", "error")
        return redirect_fn(redirect_path)
    except ValueError as exc:
        flash_fn(str(exc), "error")
        return redirect_fn(redirect_path)

    if not updated:
        flash_fn("Question not found.", "error")
        return redirect_fn(redirect_path)

    flash_fn("Question updated.", "success")
    return redirect_fn(redirect_path)


def question_delete_action(
    *,
    deps: CatalogHandlerDeps,
    question_id: int,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    redirect_path = _resolve_next_path(
        request_obj=request_obj,
        url_for_fn=url_for_fn,
        fallback_endpoint="questions",
    )
    deleted = deps.delete_question_fn(question_id)
    if not deleted:
        flash_fn("Question not found.", "error")
        return redirect_fn(redirect_path)
    flash_fn("Question deleted.", "success")
    return redirect_fn(redirect_path)


def topic_rename_action(
    *,
    deps: CatalogHandlerDeps,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    current_topic = _form_text(request_obj, "topic")
    new_topic = _form_text(request_obj, "new_topic")
    fallback_path = _resolve_next_path(
        request_obj=request_obj,
        url_for_fn=url_for_fn,
        fallback_endpoint="topics",
    )
    try:
        updated = deps.rename_topic_fn(current_topic, new_topic)
    except ValueError as exc:
        flash_fn(str(exc), "error")
        return redirect_fn(fallback_path)
    if updated <= 0:
        flash_fn("No topic was updated.", "error")
        return redirect_fn(fallback_path)
    flash_fn(f"Renamed topic for {updated} question(s).", "success")
    return redirect_fn(url_for_fn("topics", topic=new_topic))


def topic_delete_action(
    *,
    deps: CatalogHandlerDeps,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    topic = _form_text(request_obj, "topic")
    fallback_path = _resolve_next_path(
        request_obj=request_obj,
        url_for_fn=url_for_fn,
        fallback_endpoint="topics",
    )
    try:
        deleted = deps.delete_topic_fn(topic)
    except ValueError as exc:
        flash_fn(str(exc), "error")
        return redirect_fn(fallback_path)
    if deleted <= 0:
        flash_fn("No topic was deleted.", "error")
        return redirect_fn(fallback_path)
    flash_fn(f"Deleted {deleted} question(s) from topic.", "success")
    return redirect_fn(url_for_fn("topics"))


def subtopic_rename_action(
    *,
    deps: CatalogHandlerDeps,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    topic = _form_text(request_obj, "topic")
    subtopic = _form_text(request_obj, "subtopic")
    new_subtopic = _form_text(request_obj, "new_subtopic")
    fallback_path = _resolve_next_path(
        request_obj=request_obj,
        url_for_fn=url_for_fn,
        fallback_endpoint="topics",
    )
    try:
        updated = deps.rename_subtopic_fn(topic, subtopic, new_subtopic)
    except ValueError as exc:
        flash_fn(str(exc), "error")
        return redirect_fn(fallback_path)
    if updated <= 0:
        flash_fn("No subtopic was updated.", "error")
        return redirect_fn(fallback_path)
    flash_fn(f"Renamed subtopic for {updated} question(s).", "success")
    return redirect_fn(url_for_fn("topics", topic=topic, subtopic=new_subtopic))


def subtopic_delete_action(
    *,
    deps: CatalogHandlerDeps,
    request_obj,
    flash_fn,
    redirect_fn,
    url_for_fn,
):
    topic = _form_text(request_obj, "topic")
    subtopic = _form_text(request_obj, "subtopic")
    fallback_path = _resolve_next_path(
        request_obj=request_obj,
        url_for_fn=url_for_fn,
        fallback_endpoint="topics",
    )
    try:
        deleted = deps.delete_subtopic_fn(topic, subtopic)
    except ValueError as exc:
        flash_fn(str(exc), "error")
        return redirect_fn(fallback_path)
    if deleted <= 0:
        flash_fn("No subtopic was deleted.", "error")
        return redirect_fn(fallback_path)
    flash_fn(f"Deleted {deleted} question(s) from subtopic.", "success")
    return redirect_fn(url_for_fn("topics", topic=topic))
