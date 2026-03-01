from interview_app.utils import serialize_topic_subtopic

from .deps import HomeHandlerDeps


def _build_topic_filter_groups(available_topics: list[str], topic_subtopic_rows) -> list[dict]:
    grouped: dict[str, list[str]] = {topic: [] for topic in available_topics}
    for row in topic_subtopic_rows:
        topic = str(row["topic"]).strip()
        subtopic = str(row["subtopic"]).strip()
        if not topic or not subtopic:
            continue
        grouped.setdefault(topic, [])
        if subtopic not in grouped[topic]:
            grouped[topic].append(subtopic)

    ordered_topics = list(available_topics)
    for topic in sorted(grouped.keys(), key=str.lower):
        if topic not in ordered_topics:
            ordered_topics.append(topic)

    groups: list[dict] = []
    for topic in ordered_topics:
        subtopics = sorted(grouped.get(topic, []), key=str.lower)
        groups.append(
            {
                "topic": topic,
                "subtopics": [
                    {
                        "name": subtopic,
                        "value": serialize_topic_subtopic(topic, subtopic),
                    }
                    for subtopic in subtopics
                ],
            }
        )
    return groups


def index_page(*, deps: HomeHandlerDeps, render_template_fn):
    stats = deps.get_stats_fn()
    recent = deps.get_recent_questions_fn(limit=10)
    available_topics = deps.get_existing_topics_fn()
    topic_subtopic_rows = deps.list_topic_subtopics_fn(limit=500)
    topic_filter_groups = _build_topic_filter_groups(available_topics, topic_subtopic_rows)
    return render_template_fn(
        "index.html",
        stats=stats,
        recent=recent,
        available_topics=available_topics,
        topic_filter_groups=topic_filter_groups,
    )
