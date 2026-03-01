from .deps import HandlerDeps


def questions_page(*, deps: HandlerDeps, render_template_fn):
    rows = deps.list_questions_fn(limit=200)
    return render_template_fn("questions.html", questions=rows)


def topics_page(*, deps: HandlerDeps, request_obj, render_template_fn):
    selected_topic = request_obj.args.get("topic", "").strip()
    if selected_topic:
        rows = deps.list_questions_by_topic_fn(selected_topic, limit=400)
        return render_template_fn(
            "topics.html",
            selected_topic=selected_topic,
            topic_questions=rows,
        )

    rows = deps.list_topics_with_stats_fn(limit=200)
    return render_template_fn(
        "topics.html",
        topics=rows,
        selected_topic="",
        topic_questions=[],
    )
