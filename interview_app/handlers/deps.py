from dataclasses import dataclass
from typing import Any, Callable

import requests


@dataclass(frozen=True)
class HomeHandlerDeps:
    get_stats_fn: Callable[[], dict]
    get_recent_questions_fn: Callable[..., Any]
    get_existing_topics_fn: Callable[..., list[str]]
    list_topic_subtopics_fn: Callable[..., Any]


@dataclass(frozen=True)
class GenerationHandlerDeps:
    add_questions_fn: Callable[..., tuple[int, int]]
    add_code_review_questions_fn: Callable[..., tuple[int, int]]
    format_http_error_fn: Callable[[requests.HTTPError], str]
    get_recent_topic_color_fn: Callable[[str], str | None]
    get_existing_topics_fn: Callable[..., list[str]]
    list_topic_subtopics_fn: Callable[..., Any]
    list_topics_with_stats_fn: Callable[..., Any]
    list_subtopics_with_stats_fn: Callable[..., Any]
    default_generation_language_code: str
    generation_language_by_code: dict[str, str]
    generation_languages: list[tuple[str, str]]
    topic_tag_colors: list[tuple[str, str]]
    topic_tag_color_by_code: dict[str, str]
    default_topic_tag_color_code: str
    question_types: list[tuple[str, str]]


@dataclass(frozen=True)
class ReviewHandlerDeps:
    get_stats_fn: Callable[[], dict]
    get_question_by_id_fn: Callable[[int], Any]
    get_due_question_fn: Callable[..., Any]
    get_next_upcoming_fn: Callable[..., Any]
    get_latest_feedback_fn: Callable[[int], Any]
    get_review_reappearance_labels_fn: Callable[[Any], dict[str, str]]
    apply_review_fn: Callable[[int, int], None]
    normalize_topic_filters_fn: Callable[[list[str]], list[str]]
    normalize_subtopic_filters_fn: Callable[[list[str]], list[tuple[str, str]]]
    serialize_topic_subtopic_filter_fn: Callable[[str, str], str]
    is_randomized_review_fn: Callable[[str], bool]
    extract_review_filters_from_referrer_fn: Callable[[], tuple[list[str], list[tuple[str, str]], bool]]
    review_redirect_fn: Callable[..., Any]
    generate_answer_for_question_fn: Callable[[int], str]
    call_gemini_for_feedback_fn: Callable[..., dict]
    call_gemini_for_code_review_feedback_fn: Callable[..., dict]
    save_feedback_fn: Callable[[int, str, dict], None]
    normalize_audio_mime_type_fn: Callable[[str], str | None]
    call_gemini_for_transcription_fn: Callable[[bytes, str], str]
    format_http_error_fn: Callable[[requests.HTTPError], str]
    max_inline_audio_bytes: int


@dataclass(frozen=True)
class CatalogHandlerDeps:
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
class HandlerDepsBundle:
    home: HomeHandlerDeps
    generation: GenerationHandlerDeps
    review: ReviewHandlerDeps
    catalog: CatalogHandlerDeps
