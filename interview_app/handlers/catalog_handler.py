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
