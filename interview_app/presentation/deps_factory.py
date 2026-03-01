from types import ModuleType

from interview_app.handlers.deps import HandlerDeps


def build_handler_deps_from_namespace(namespace: ModuleType) -> HandlerDeps:
    return HandlerDeps(
        get_stats_fn=namespace.get_stats,
        get_recent_questions_fn=namespace.get_recent_questions,
        get_existing_topics_fn=namespace.get_existing_topics,
        add_questions_fn=namespace.add_questions,
        format_http_error_fn=namespace.format_http_error,
        get_recent_topic_color_fn=namespace.get_recent_topic_color,
        get_question_by_id_fn=namespace.get_question_by_id,
        get_due_question_fn=namespace.get_due_question,
        get_next_upcoming_fn=namespace.get_next_upcoming,
        get_latest_feedback_fn=namespace.get_latest_feedback,
        apply_review_fn=namespace.apply_review,
        normalize_topic_filters_fn=namespace.normalize_topic_filters,
        is_randomized_review_fn=namespace.is_randomized_review,
        extract_review_filters_from_referrer_fn=namespace.extract_review_filters_from_referrer,
        review_redirect_fn=namespace.review_redirect,
        generate_answer_for_question_fn=namespace.generate_answer_for_question,
        call_gemini_for_feedback_fn=namespace.call_gemini_for_feedback,
        save_feedback_fn=namespace.save_feedback,
        normalize_audio_mime_type_fn=namespace.normalize_audio_mime_type,
        call_gemini_for_transcription_fn=namespace.call_gemini_for_transcription,
        list_questions_fn=namespace.list_questions,
        list_questions_by_topic_fn=namespace.list_questions_by_topic,
        list_topics_with_stats_fn=namespace.list_topics_with_stats,
        default_generation_language_code=namespace.DEFAULT_GENERATION_LANGUAGE_CODE,
        generation_language_by_code=namespace.GENERATION_LANGUAGE_BY_CODE,
        generation_languages=namespace.GENERATION_LANGUAGES,
        topic_tag_colors=namespace.TOPIC_TAG_COLORS,
        topic_tag_color_by_code=namespace.TOPIC_TAG_COLOR_BY_CODE,
        default_topic_tag_color_code=namespace.DEFAULT_TOPIC_TAG_COLOR_CODE,
        max_inline_audio_bytes=namespace.MAX_INLINE_AUDIO_BYTES,
    )
