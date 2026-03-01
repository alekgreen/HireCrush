from dataclasses import dataclass
from types import ModuleType
from typing import Any, Callable

from interview_app.handlers.deps import (
    CatalogHandlerDeps,
    GenerationHandlerDeps,
    HandlerDepsBundle,
    HomeHandlerDeps,
    ReviewHandlerDeps,
)


@dataclass(frozen=True)
class HomeQueryInputs:
    get_stats_fn: Callable[[], dict]
    get_recent_questions_fn: Callable[..., Any]
    get_existing_topics_fn: Callable[..., list[str]]
    list_topic_subtopics_fn: Callable[..., Any]


@dataclass(frozen=True)
class GenerationFlowInputs:
    add_questions_fn: Callable[..., tuple[int, int]]
    add_code_review_questions_fn: Callable[..., tuple[int, int]]
    format_http_error_fn: Callable[..., str]
    get_recent_topic_color_fn: Callable[[str], str | None]
    get_existing_topics_fn: Callable[..., list[str]]
    list_topic_subtopics_fn: Callable[..., Any]
    list_topics_with_stats_fn: Callable[..., Any]
    list_subtopics_with_stats_fn: Callable[..., Any]


@dataclass(frozen=True)
class ReviewFlowInputs:
    get_question_by_id_fn: Callable[[int], Any]
    get_due_question_fn: Callable[..., Any]
    get_next_upcoming_fn: Callable[..., Any]
    get_latest_feedback_fn: Callable[[int], Any]
    get_review_reappearance_labels_fn: Callable[[Any], dict[str, str]]
    get_stats_fn: Callable[[], dict]
    apply_review_fn: Callable[[int, int], None]
    normalize_topic_filters_fn: Callable[[list[str]], list[str]]
    normalize_subtopic_filters_fn: Callable[[list[str]], list[tuple[str, str]]]
    serialize_topic_subtopic_filter_fn: Callable[[str, str], str]
    is_randomized_review_fn: Callable[[str], bool]
    extract_review_filters_from_referrer_fn: Callable[
        [],
        tuple[list[str], list[tuple[str, str]], bool],
    ]
    review_redirect_fn: Callable[..., Any]
    generate_answer_for_question_fn: Callable[[int], str]
    call_gemini_for_feedback_fn: Callable[..., dict]
    call_gemini_for_code_review_feedback_fn: Callable[..., dict]
    save_feedback_fn: Callable[[int, str, dict], None]
    normalize_audio_mime_type_fn: Callable[[str], str | None]
    call_gemini_for_transcription_fn: Callable[[bytes, str], str]


@dataclass(frozen=True)
class CatalogQueryInputs:
    list_questions_fn: Callable[..., Any]
    list_questions_by_topic_fn: Callable[..., Any]
    list_questions_by_subtopic_fn: Callable[..., Any]
    list_topics_with_stats_fn: Callable[..., Any]
    list_subtopics_with_stats_fn: Callable[..., Any]
    update_question_fn: Callable[..., bool]
    delete_question_fn: Callable[[int], bool]
    rename_topic_fn: Callable[[str, str], int]
    update_topic_color_fn: Callable[[str, str], int]
    delete_topic_fn: Callable[[str], int]
    rename_subtopic_fn: Callable[[str, str, str], int]
    update_subtopic_color_fn: Callable[[str, str, str], int]
    delete_subtopic_fn: Callable[[str, str], int]


@dataclass(frozen=True)
class PresentationOptions:
    default_generation_language_code: str
    generation_language_by_code: dict[str, str]
    generation_languages: list[tuple[str, str]]
    topic_tag_colors: list[tuple[str, str]]
    topic_tag_color_by_code: dict[str, str]
    default_topic_tag_color_code: str
    max_inline_audio_bytes: int
    question_types: list[tuple[str, str]]


@dataclass(frozen=True)
class HandlerDepsInputs:
    home: HomeQueryInputs
    generation: GenerationFlowInputs
    review: ReviewFlowInputs
    catalog: CatalogQueryInputs
    options: PresentationOptions


def build_handler_deps_bundle(
    *,
    inputs: HandlerDepsInputs,
) -> HandlerDepsBundle:
    return HandlerDepsBundle(
        home=HomeHandlerDeps(
            get_stats_fn=inputs.home.get_stats_fn,
            get_recent_questions_fn=inputs.home.get_recent_questions_fn,
            get_existing_topics_fn=inputs.home.get_existing_topics_fn,
            list_topic_subtopics_fn=inputs.home.list_topic_subtopics_fn,
        ),
        generation=GenerationHandlerDeps(
            add_questions_fn=inputs.generation.add_questions_fn,
            add_code_review_questions_fn=inputs.generation.add_code_review_questions_fn,
            format_http_error_fn=inputs.generation.format_http_error_fn,
            get_recent_topic_color_fn=inputs.generation.get_recent_topic_color_fn,
            get_existing_topics_fn=inputs.generation.get_existing_topics_fn,
            list_topic_subtopics_fn=inputs.generation.list_topic_subtopics_fn,
            list_topics_with_stats_fn=inputs.generation.list_topics_with_stats_fn,
            list_subtopics_with_stats_fn=inputs.generation.list_subtopics_with_stats_fn,
            default_generation_language_code=inputs.options.default_generation_language_code,
            generation_language_by_code=inputs.options.generation_language_by_code,
            generation_languages=inputs.options.generation_languages,
            topic_tag_colors=inputs.options.topic_tag_colors,
            topic_tag_color_by_code=inputs.options.topic_tag_color_by_code,
            default_topic_tag_color_code=inputs.options.default_topic_tag_color_code,
            question_types=inputs.options.question_types,
        ),
        review=ReviewHandlerDeps(
            get_stats_fn=inputs.review.get_stats_fn,
            get_question_by_id_fn=inputs.review.get_question_by_id_fn,
            get_due_question_fn=inputs.review.get_due_question_fn,
            get_next_upcoming_fn=inputs.review.get_next_upcoming_fn,
            get_latest_feedback_fn=inputs.review.get_latest_feedback_fn,
            get_review_reappearance_labels_fn=inputs.review.get_review_reappearance_labels_fn,
            apply_review_fn=inputs.review.apply_review_fn,
            normalize_topic_filters_fn=inputs.review.normalize_topic_filters_fn,
            normalize_subtopic_filters_fn=inputs.review.normalize_subtopic_filters_fn,
            serialize_topic_subtopic_filter_fn=inputs.review.serialize_topic_subtopic_filter_fn,
            is_randomized_review_fn=inputs.review.is_randomized_review_fn,
            extract_review_filters_from_referrer_fn=inputs.review.extract_review_filters_from_referrer_fn,
            review_redirect_fn=inputs.review.review_redirect_fn,
            generate_answer_for_question_fn=inputs.review.generate_answer_for_question_fn,
            call_gemini_for_feedback_fn=inputs.review.call_gemini_for_feedback_fn,
            call_gemini_for_code_review_feedback_fn=inputs.review.call_gemini_for_code_review_feedback_fn,
            save_feedback_fn=inputs.review.save_feedback_fn,
            normalize_audio_mime_type_fn=inputs.review.normalize_audio_mime_type_fn,
            call_gemini_for_transcription_fn=inputs.review.call_gemini_for_transcription_fn,
            format_http_error_fn=inputs.generation.format_http_error_fn,
            max_inline_audio_bytes=inputs.options.max_inline_audio_bytes,
        ),
        catalog=CatalogHandlerDeps(
            list_questions_fn=inputs.catalog.list_questions_fn,
            list_questions_by_topic_fn=inputs.catalog.list_questions_by_topic_fn,
            list_questions_by_subtopic_fn=inputs.catalog.list_questions_by_subtopic_fn,
            list_topics_with_stats_fn=inputs.catalog.list_topics_with_stats_fn,
            list_subtopics_with_stats_fn=inputs.catalog.list_subtopics_with_stats_fn,
            update_question_fn=inputs.catalog.update_question_fn,
            delete_question_fn=inputs.catalog.delete_question_fn,
            rename_topic_fn=inputs.catalog.rename_topic_fn,
            update_topic_color_fn=inputs.catalog.update_topic_color_fn,
            delete_topic_fn=inputs.catalog.delete_topic_fn,
            rename_subtopic_fn=inputs.catalog.rename_subtopic_fn,
            update_subtopic_color_fn=inputs.catalog.update_subtopic_color_fn,
            delete_subtopic_fn=inputs.catalog.delete_subtopic_fn,
        ),
    )


def build_handler_deps_from_namespace(namespace: ModuleType) -> HandlerDepsBundle:
    return build_handler_deps_bundle(
        inputs=HandlerDepsInputs(
            home=HomeQueryInputs(
                get_stats_fn=namespace.get_stats,
                get_recent_questions_fn=namespace.get_recent_questions,
                get_existing_topics_fn=namespace.get_existing_topics,
                list_topic_subtopics_fn=namespace.list_topic_subtopics,
            ),
            generation=GenerationFlowInputs(
                add_questions_fn=namespace.add_questions,
                add_code_review_questions_fn=namespace.add_code_review_questions,
                format_http_error_fn=namespace.format_http_error,
                get_recent_topic_color_fn=namespace.get_recent_topic_color,
                get_existing_topics_fn=namespace.get_existing_topics,
                list_topic_subtopics_fn=namespace.list_topic_subtopics,
                list_topics_with_stats_fn=namespace.list_topics_with_stats,
                list_subtopics_with_stats_fn=namespace.list_subtopics_with_stats,
            ),
            review=ReviewFlowInputs(
                get_question_by_id_fn=namespace.get_question_by_id,
                get_due_question_fn=namespace.get_due_question,
                get_next_upcoming_fn=namespace.get_next_upcoming,
                get_latest_feedback_fn=namespace.get_latest_feedback,
                get_review_reappearance_labels_fn=namespace.get_review_reappearance_labels,
                get_stats_fn=namespace.get_stats,
                apply_review_fn=namespace.apply_review,
                normalize_topic_filters_fn=namespace.normalize_topic_filters,
                normalize_subtopic_filters_fn=namespace.normalize_subtopic_filters,
                serialize_topic_subtopic_filter_fn=namespace.serialize_topic_subtopic_filter,
                is_randomized_review_fn=namespace.is_randomized_review,
                extract_review_filters_from_referrer_fn=namespace.extract_review_filters_from_referrer,
                review_redirect_fn=namespace.review_redirect,
                generate_answer_for_question_fn=namespace.generate_answer_for_question,
                call_gemini_for_feedback_fn=namespace.call_gemini_for_feedback,
                call_gemini_for_code_review_feedback_fn=namespace.call_gemini_for_code_review_feedback,
                save_feedback_fn=namespace.save_feedback,
                normalize_audio_mime_type_fn=namespace.normalize_audio_mime_type,
                call_gemini_for_transcription_fn=namespace.call_gemini_for_transcription,
            ),
            catalog=CatalogQueryInputs(
                list_questions_fn=namespace.list_questions,
                list_questions_by_topic_fn=namespace.list_questions_by_topic,
                list_questions_by_subtopic_fn=namespace.list_questions_by_subtopic,
                list_topics_with_stats_fn=namespace.list_topics_with_stats,
                list_subtopics_with_stats_fn=namespace.list_subtopics_with_stats,
                update_question_fn=namespace.update_question,
                delete_question_fn=namespace.delete_question,
                rename_topic_fn=namespace.rename_topic,
                update_topic_color_fn=namespace.update_topic_color,
                delete_topic_fn=namespace.delete_topic,
                rename_subtopic_fn=namespace.rename_subtopic,
                update_subtopic_color_fn=namespace.update_subtopic_color,
                delete_subtopic_fn=namespace.delete_subtopic,
            ),
            options=PresentationOptions(
                default_generation_language_code=namespace.DEFAULT_GENERATION_LANGUAGE_CODE,
                generation_language_by_code=namespace.GENERATION_LANGUAGE_BY_CODE,
                generation_languages=namespace.GENERATION_LANGUAGES,
                topic_tag_colors=namespace.TOPIC_TAG_COLORS,
                topic_tag_color_by_code=namespace.TOPIC_TAG_COLOR_BY_CODE,
                default_topic_tag_color_code=namespace.DEFAULT_TOPIC_TAG_COLOR_CODE,
                max_inline_audio_bytes=namespace.MAX_INLINE_AUDIO_BYTES,
                question_types=namespace.QUESTION_TYPES,
            ),
        ),
    )
