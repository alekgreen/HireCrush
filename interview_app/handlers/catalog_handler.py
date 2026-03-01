import sqlite3

from interview_app.constants import TOPIC_TAG_COLOR_BY_CODE

from .deps import CatalogHandlerDeps

PAGINATION_PAGE_SIZES = (25, 50, 100)
DEFAULT_PER_PAGE = PAGINATION_PAGE_SIZES[0]


def _build_topic_subtopics(subtopic_rows) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for row in subtopic_rows:
        topic = str(row["topic"]).strip()
        if not topic:
            continue
        grouped.setdefault(topic, []).append(row)
    return grouped


def _normalize_color_code(value: str | None) -> str:
    code = str(value or "").strip().lower()
    if not code:
        return ""
    if code not in TOPIC_TAG_COLOR_BY_CODE:
        return ""
    return code


def _resolve_topic_color(*, rows, subtopic_rows) -> str:
    if rows:
        color = _normalize_color_code(rows[0]["topic_color"] if "topic_color" in rows[0].keys() else "")
        if color:
            return color
    if subtopic_rows:
        color = _normalize_color_code(subtopic_rows[0]["topic_color"] if "topic_color" in subtopic_rows[0].keys() else "")
        if color:
            return color
    return ""


def _resolve_subtopic_color(*, selected_subtopic: str, rows, subtopic_rows) -> str:
    selected_key = selected_subtopic.strip().lower()
    if selected_key:
        for row in subtopic_rows:
            row_subtopic = str(row["subtopic"]).strip().lower()
            if row_subtopic != selected_key:
                continue
            color = _normalize_color_code(row["subtopic_color"] if "subtopic_color" in row.keys() else "")
            if color:
                return color
    if rows and selected_key:
        color = _normalize_color_code(rows[0]["subtopic_color"] if "subtopic_color" in rows[0].keys() else "")
        if color:
            return color
    return ""


def _parse_positive_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return parsed


def _parse_pagination(request_obj) -> tuple[int, int, int]:
    per_page = _parse_positive_int(request_obj.args.get("per_page", ""), DEFAULT_PER_PAGE)
    if per_page not in PAGINATION_PAGE_SIZES:
        per_page = DEFAULT_PER_PAGE
    page = _parse_positive_int(request_obj.args.get("page", ""), 1)
    offset = (page - 1) * per_page
    return page, per_page, offset


def _slice_page(rows, *, per_page: int) -> tuple[list, bool]:
    row_list = list(rows)
    has_next = len(row_list) > per_page
    return row_list[:per_page], has_next


def questions_page(*, deps: CatalogHandlerDeps, request_obj, render_template_fn):
    page, per_page, offset = _parse_pagination(request_obj)
    rows = deps.list_questions_fn(limit=per_page + 1, offset=offset)
    page_rows, has_next = _slice_page(rows, per_page=per_page)
    return render_template_fn(
        "questions.html",
        questions=page_rows,
        page=page,
        per_page=per_page,
        per_page_options=PAGINATION_PAGE_SIZES,
        has_prev=page > 1,
        has_next=has_next,
    )


def topics_page(*, deps: CatalogHandlerDeps, request_obj, render_template_fn):
    selected_topic = request_obj.args.get("topic", "").strip()
    selected_subtopic = request_obj.args.get("subtopic", "").strip()
    if selected_topic:
        page, per_page, offset = _parse_pagination(request_obj)
        if selected_subtopic:
            rows = deps.list_questions_by_subtopic_fn(
                selected_topic,
                selected_subtopic,
                limit=per_page + 1,
                offset=offset,
            )
        else:
            rows = deps.list_questions_by_topic_fn(selected_topic, limit=per_page + 1, offset=offset)
        page_rows, has_next = _slice_page(rows, per_page=per_page)
        subtopic_rows = deps.list_subtopics_with_stats_fn(topic=selected_topic, limit=400)
        return render_template_fn(
            "topics.html",
            selected_topic=selected_topic,
            selected_subtopic=selected_subtopic,
            topic_questions=page_rows,
            topic_subtopics=_build_topic_subtopics(subtopic_rows),
            selected_topic_color=_resolve_topic_color(rows=page_rows, subtopic_rows=subtopic_rows),
            selected_subtopic_color=_resolve_subtopic_color(
                selected_subtopic=selected_subtopic,
                rows=page_rows,
                subtopic_rows=subtopic_rows,
            ),
            page=page,
            per_page=per_page,
            per_page_options=PAGINATION_PAGE_SIZES,
            has_prev=page > 1,
            has_next=has_next,
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
        selected_topic_color="",
        selected_subtopic_color="",
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
    next_topic = new_topic or current_topic
    topic_color = _form_text(request_obj, "topic_color").lower()
    fallback_path = _resolve_next_path(
        request_obj=request_obj,
        url_for_fn=url_for_fn,
        fallback_endpoint="topics",
    )
    if topic_color and topic_color not in TOPIC_TAG_COLOR_BY_CODE:
        flash_fn("Topic tag color is invalid.", "error")
        return redirect_fn(fallback_path)
    if not deps.list_questions_by_topic_fn(current_topic, limit=1):
        flash_fn("No topic was updated.", "error")
        return redirect_fn(fallback_path)

    renamed_count = 0
    recolored_count = 0
    try:
        if next_topic != current_topic:
            renamed_count = deps.rename_topic_fn(current_topic, next_topic)
        if topic_color:
            recolored_count = deps.update_topic_color_fn(next_topic, topic_color)
    except ValueError as exc:
        flash_fn(str(exc), "error")
        return redirect_fn(fallback_path)

    if next_topic != current_topic and renamed_count <= 0 and not topic_color:
        flash_fn("No topic was updated.", "error")
        return redirect_fn(fallback_path)

    if next_topic != current_topic and topic_color:
        flash_fn(
            f"Renamed topic for {renamed_count} question(s) and updated color for {recolored_count} question(s).",
            "success",
        )
    elif next_topic != current_topic:
        flash_fn(f"Renamed topic for {renamed_count} question(s).", "success")
    elif topic_color:
        if recolored_count > 0:
            flash_fn(f"Updated topic color for {recolored_count} question(s).", "success")
        else:
            flash_fn("Topic color unchanged.", "success")
    else:
        flash_fn("No topic changes were submitted.", "error")
        return redirect_fn(fallback_path)

    return redirect_fn(url_for_fn("topics", topic=next_topic))


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
    next_subtopic = new_subtopic or subtopic
    subtopic_color = _form_text(request_obj, "subtopic_color").lower()
    fallback_path = _resolve_next_path(
        request_obj=request_obj,
        url_for_fn=url_for_fn,
        fallback_endpoint="topics",
    )
    if subtopic_color and subtopic_color not in TOPIC_TAG_COLOR_BY_CODE:
        flash_fn("Subtopic tag color is invalid.", "error")
        return redirect_fn(fallback_path)
    if not deps.list_questions_by_subtopic_fn(topic, subtopic, limit=1):
        flash_fn("No subtopic was updated.", "error")
        return redirect_fn(fallback_path)

    renamed_count = 0
    recolored_count = 0
    try:
        if next_subtopic != subtopic:
            renamed_count = deps.rename_subtopic_fn(topic, subtopic, next_subtopic)
        if subtopic_color:
            recolored_count = deps.update_subtopic_color_fn(topic, next_subtopic, subtopic_color)
    except ValueError as exc:
        flash_fn(str(exc), "error")
        return redirect_fn(fallback_path)

    if next_subtopic != subtopic and renamed_count <= 0 and not subtopic_color:
        flash_fn("No subtopic was updated.", "error")
        return redirect_fn(fallback_path)

    if next_subtopic != subtopic and subtopic_color:
        flash_fn(
            f"Renamed subtopic for {renamed_count} question(s) and updated color for {recolored_count} question(s).",
            "success",
        )
    elif next_subtopic != subtopic:
        flash_fn(f"Renamed subtopic for {renamed_count} question(s).", "success")
    elif subtopic_color:
        if recolored_count > 0:
            flash_fn(f"Updated subtopic color for {recolored_count} question(s).", "success")
        else:
            flash_fn("Subtopic color unchanged.", "success")
    else:
        flash_fn("No subtopic changes were submitted.", "error")
        return redirect_fn(fallback_path)

    return redirect_fn(url_for_fn("topics", topic=topic, subtopic=next_subtopic))


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
