from .deps import HomeHandlerDeps


def index_page(*, deps: HomeHandlerDeps, render_template_fn):
    stats = deps.get_stats_fn()
    recent = deps.get_recent_questions_fn(limit=10)
    available_topics = deps.get_existing_topics_fn()
    return render_template_fn(
        "index.html",
        stats=stats,
        recent=recent,
        available_topics=available_topics,
    )
