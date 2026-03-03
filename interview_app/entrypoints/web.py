import os
from inspect import Parameter, signature
from typing import Any

import click
import requests
from flask import redirect, request, url_for

from interview_app.application.runtime_facade import (
    RuntimeCallables,
    RuntimeConfigDeps,
    RuntimeDependencies,
    RuntimeFacade,
    RuntimeInfraDeps,
    RuntimeParserDeps,
    RuntimeRepositoryDeps,
    RuntimeServiceModules,
    RuntimeUtilityDeps,
)
from interview_app.adapters.persistence.sqlite.repositories import (
    SQLiteFeedbackRepository,
    SQLiteQuestionRepository,
)
from interview_app.adapters.persistence.sqlite.settings_repository import SQLiteSettingsRepository
from interview_app.constants import (
    ANSWER_JSON_SCHEMA,
    CODE_REVIEW_QUESTION_SCHEMA,
    DEFAULT_GENERATION_LANGUAGE_CODE,
    DEFAULT_TOPIC_TAG_COLOR_CODE,
    FEEDBACK_JSON_SCHEMA,
    GEMINI_MODEL_FALLBACKS,
    GENERATION_LANGUAGES,
    GENERATION_LANGUAGE_BY_CODE,
    QUESTION_TYPES,
    QUESTIONS_JSON_SCHEMA,
    TOPIC_TAG_COLORS,
    TOPIC_TAG_COLOR_BY_CODE,
)
from interview_app.db import (
    close_db,
    get_db,
    list_applied_migrations,
    list_known_migrations,
    list_pending_migrations,
    run_migrations,
)
from interview_app.presentation.app_factory import create_flask_app
from interview_app.presentation.deps_factory import (
    CatalogQueryInputs,
    GenerationFlowInputs,
    HandlerDepsInputs,
    HomeQueryInputs,
    PresentationOptions,
    ReviewFlowInputs,
    build_handler_deps_bundle,
)
from interview_app.presentation.routes import register_routes
from interview_app.services import (
    gemini_service,
    generation_service,
    question_service,
    review_service,
    secure_token_store,
)
from interview_app.utils import (
    clean_question_text,
    iso,
    now_utc,
    parse_gemini_questions,
    parse_json_from_text,
    question_hash,
)


def _supports_get_db_kwarg(factory: Any) -> bool:
    try:
        params = signature(factory).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        p.kind == Parameter.VAR_KEYWORD or p.name == "get_db_fn"
        for p in params
    )


def _build_repository(factory: Any, *, get_db_fn):
    if _supports_get_db_kwarg(factory):
        return factory(get_db_fn=get_db_fn)
    return factory()


def _normalized_or_none(value: object) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def create_app(config_override: dict[str, Any] | None = None, import_name: str = "app"):
    close_db_fn = close_db
    if config_override and "CLOSE_DB_FN" in config_override:
        close_db_fn = config_override["CLOSE_DB_FN"]

    app = create_flask_app(import_name, close_db_fn=close_db_fn)
    if config_override:
        app.config.update(config_override)

    get_db_fn = app.config.get("GET_DB_FN", get_db)
    run_migrations_fn = app.config.get("RUN_MIGRATIONS_FN", run_migrations)
    list_known_migrations_fn = app.config.get("LIST_KNOWN_MIGRATIONS_FN", list_known_migrations)
    list_applied_migrations_fn = app.config.get("LIST_APPLIED_MIGRATIONS_FN", list_applied_migrations)
    list_pending_migrations_fn = app.config.get("LIST_PENDING_MIGRATIONS_FN", list_pending_migrations)

    question_repository_factory = app.config.get("QUESTION_REPOSITORY_FACTORY", SQLiteQuestionRepository)
    feedback_repository_factory = app.config.get("FEEDBACK_REPOSITORY_FACTORY", SQLiteFeedbackRepository)
    settings_repository_factory = app.config.get("SETTINGS_REPOSITORY_FACTORY", SQLiteSettingsRepository)

    question_repository = _build_repository(question_repository_factory, get_db_fn=get_db_fn)
    feedback_repository = _build_repository(feedback_repository_factory, get_db_fn=get_db_fn)
    settings_repository = _build_repository(settings_repository_factory, get_db_fn=get_db_fn)

    resolve_gemini_model_fn = app.config.get("RESOLVE_GEMINI_MODEL_FN")
    if not callable(resolve_gemini_model_fn):
        def resolve_gemini_model_fn() -> str | None:
            stored = settings_repository.get_value("gemini_model")
            if stored:
                return stored
            return _normalized_or_none(app.config.get("GEMINI_MODEL", ""))

    persist_gemini_model_fn = app.config.get("PERSIST_GEMINI_MODEL_FN")
    if not callable(persist_gemini_model_fn):
        def persist_gemini_model_fn(model: str) -> None:
            settings_repository.set_value("gemini_model", model)

    resolve_gemini_api_key_fn = app.config.get("RESOLVE_GEMINI_API_KEY_FN")
    if not callable(resolve_gemini_api_key_fn):
        def resolve_gemini_api_key_fn() -> str | None:
            stored = secure_token_store.get_gemini_api_key()
            if stored:
                return stored
            return _normalized_or_none(app.config.get("GEMINI_API_KEY", ""))

    persist_gemini_api_key_fn = app.config.get("PERSIST_GEMINI_API_KEY_FN")
    if not callable(persist_gemini_api_key_fn):
        persist_gemini_api_key_fn = secure_token_store.set_gemini_api_key

    clear_gemini_api_key_fn = app.config.get("CLEAR_GEMINI_API_KEY_FN")
    if not callable(clear_gemini_api_key_fn):
        clear_gemini_api_key_fn = secure_token_store.clear_gemini_api_key

    gemini_api_key_store_available_fn = app.config.get("GEMINI_API_KEY_STORE_AVAILABLE_FN")
    if not callable(gemini_api_key_store_available_fn):
        gemini_api_key_store_available_fn = secure_token_store.keyring_available

    gemini_api_key_store_mode_fn = app.config.get("GEMINI_API_KEY_STORE_MODE_FN")
    if not callable(gemini_api_key_store_mode_fn):
        gemini_api_key_store_mode_fn = secure_token_store.backend_mode

    gemini_api_key_store_uses_alt_fallback_fn = app.config.get("GEMINI_API_KEY_STORE_USES_ALT_FALLBACK_FN")
    if not callable(gemini_api_key_store_uses_alt_fallback_fn):
        gemini_api_key_store_uses_alt_fallback_fn = secure_token_store.using_keyrings_alt_fallback

    explicit_model_override = bool(config_override and "GEMINI_MODEL" in config_override)
    explicit_api_key_override = bool(config_override and "GEMINI_API_KEY" in config_override)
    if not explicit_model_override:
        with app.app_context():
            persisted_model = resolve_gemini_model_fn()
        if persisted_model:
            app.config["GEMINI_MODEL"] = persisted_model
    if not explicit_api_key_override:
        with app.app_context():
            persisted_api_key = resolve_gemini_api_key_fn()
        if persisted_api_key:
            app.config["GEMINI_API_KEY"] = persisted_api_key

    runtime_ref: dict[str, RuntimeFacade] = {}
    runtime_callables = RuntimeCallables(
        get_gemini_generate_json=lambda: runtime_ref["runtime"].gemini_generate_json,
        get_normalize_audio_mime_type=lambda: runtime_ref["runtime"].normalize_audio_mime_type,
        get_call_gemini_for_questions=lambda: runtime_ref["runtime"].call_gemini_for_questions,
        get_call_gemini_for_answer=lambda: runtime_ref["runtime"].call_gemini_for_answer,
        get_call_gemini_for_code_review_questions=lambda: runtime_ref["runtime"].call_gemini_for_code_review_questions,
    )
    runtime_deps = RuntimeDependencies(
        infra=RuntimeInfraDeps(
            os_getenv=os.getenv,
            requests_module=requests,
            get_db_fn=get_db_fn,
        ),
        modules=RuntimeServiceModules(
            gemini_service_module=gemini_service,
            generation_service_module=generation_service,
            question_service_module=question_service,
            review_service_module=review_service,
        ),
        parsers=RuntimeParserDeps(
            parse_json_from_text_fn=parse_json_from_text,
            parse_gemini_questions_fn=parse_gemini_questions,
        ),
        repositories=RuntimeRepositoryDeps(
            question_repository=question_repository,
        ),
        utils=RuntimeUtilityDeps(
            clean_question_text_fn=clean_question_text,
            question_hash_fn=question_hash,
            now_utc_fn=now_utc,
            iso_fn=iso,
        ),
        config=RuntimeConfigDeps(
            gemini_model_fallbacks=GEMINI_MODEL_FALLBACKS,
            questions_json_schema=QUESTIONS_JSON_SCHEMA,
            answer_json_schema=ANSWER_JSON_SCHEMA,
            feedback_json_schema=FEEDBACK_JSON_SCHEMA,
            code_review_question_schema=CODE_REVIEW_QUESTION_SCHEMA,
            default_topic_tag_color_code=DEFAULT_TOPIC_TAG_COLOR_CODE,
            max_inline_audio_bytes=gemini_service.MAX_INLINE_AUDIO_BYTES,
        ),
    )
    runtime = RuntimeFacade(
        app=app,
        deps=runtime_deps,
        runtime_callables=runtime_callables,
    )
    runtime_ref["runtime"] = runtime

    def review_redirect(
        topics: list[str] | None = None,
        subtopics: list[tuple[str, str]] | None = None,
        randomize: bool = False,
        qid: int | None = None,
        show_feedback: bool = False,
        skip_qid: int | None = None,
    ):
        return runtime.review_redirect(
            topics=topics,
            subtopics=subtopics,
            randomize=randomize,
            qid=qid,
            show_feedback=show_feedback,
            skip_qid=skip_qid,
            redirect_fn=redirect,
            url_for_fn=url_for,
        )

    def extract_review_filters_from_referrer() -> tuple[list[str], list[tuple[str, str]], bool]:
        return runtime.extract_review_filters_from_referrer(request.referrer or "")

    default_handler_deps_bundle = build_handler_deps_bundle(
        inputs=HandlerDepsInputs(
            home=HomeQueryInputs(
                get_stats_fn=question_repository.get_stats,
                get_recent_questions_fn=question_repository.get_recent_questions,
                get_existing_topics_fn=question_repository.get_existing_topics,
                list_topic_subtopics_fn=question_repository.list_topic_subtopics,
            ),
            generation=GenerationFlowInputs(
                add_questions_fn=runtime.add_questions,
                add_code_review_questions_fn=runtime.add_code_review_questions,
                format_http_error_fn=runtime.format_http_error,
                get_recent_topic_color_fn=question_repository.get_recent_topic_color,
                get_existing_topics_fn=question_repository.get_existing_topics,
                list_topic_subtopics_fn=question_repository.list_topic_subtopics,
                list_topics_with_stats_fn=question_repository.list_topics_with_stats,
                list_subtopics_with_stats_fn=question_repository.list_subtopics_with_stats,
            ),
            review=ReviewFlowInputs(
                get_question_by_id_fn=question_repository.get_question_by_id,
                get_due_question_fn=question_repository.get_due_question,
                get_next_upcoming_fn=question_repository.get_next_upcoming,
                get_latest_feedback_fn=feedback_repository.get_latest_feedback,
                get_review_reappearance_labels_fn=runtime.get_review_reappearance_labels,
                get_stats_fn=question_repository.get_stats,
                apply_review_fn=runtime.apply_review,
                normalize_topic_filters_fn=runtime.normalize_topic_filters,
                normalize_subtopic_filters_fn=runtime.normalize_subtopic_filters,
                serialize_topic_subtopic_filter_fn=runtime.serialize_topic_subtopic_filter,
                is_randomized_review_fn=runtime.is_randomized_review,
                extract_review_filters_from_referrer_fn=extract_review_filters_from_referrer,
                review_redirect_fn=review_redirect,
                generate_answer_for_question_fn=runtime.generate_answer_for_question,
                call_gemini_for_feedback_fn=runtime.call_gemini_for_feedback,
                call_gemini_for_code_review_feedback_fn=runtime.call_gemini_for_code_review_feedback,
                save_feedback_fn=feedback_repository.save_feedback,
                normalize_audio_mime_type_fn=runtime.normalize_audio_mime_type,
                call_gemini_for_transcription_fn=runtime.call_gemini_for_transcription,
            ),
            catalog=CatalogQueryInputs(
                list_questions_fn=question_repository.list_questions,
                list_questions_by_topic_fn=question_repository.list_questions_by_topic,
                list_questions_by_subtopic_fn=question_repository.list_questions_by_subtopic,
                list_topics_with_stats_fn=question_repository.list_topics_with_stats,
                list_subtopics_with_stats_fn=question_repository.list_subtopics_with_stats,
                update_question_fn=question_repository.update_question,
                delete_question_fn=question_repository.delete_question,
                rename_topic_fn=question_repository.rename_topic,
                update_topic_color_fn=question_repository.update_topic_color,
                delete_topic_fn=question_repository.delete_topic,
                rename_subtopic_fn=question_repository.rename_subtopic,
                update_subtopic_color_fn=question_repository.update_subtopic_color,
                delete_subtopic_fn=question_repository.delete_subtopic,
            ),
            options=PresentationOptions(
                default_generation_language_code=DEFAULT_GENERATION_LANGUAGE_CODE,
                generation_language_by_code=GENERATION_LANGUAGE_BY_CODE,
                generation_languages=GENERATION_LANGUAGES,
                topic_tag_colors=TOPIC_TAG_COLORS,
                topic_tag_color_by_code=TOPIC_TAG_COLOR_BY_CODE,
                default_topic_tag_color_code=DEFAULT_TOPIC_TAG_COLOR_CODE,
                max_inline_audio_bytes=gemini_service.MAX_INLINE_AUDIO_BYTES,
                question_types=QUESTION_TYPES,
            ),
        ),
    )

    def build_handler_deps():
        override = app.config.get("HANDLER_DEPS_OVERRIDE")
        if override is not None:
            return override
        return default_handler_deps_bundle

    app.extensions["runtime"] = runtime
    app.extensions["build_handler_deps"] = build_handler_deps
    app.extensions["settings_repository"] = settings_repository
    app.extensions["resolve_gemini_model_fn"] = resolve_gemini_model_fn
    app.extensions["persist_gemini_model_fn"] = persist_gemini_model_fn
    app.extensions["resolve_gemini_api_key_fn"] = resolve_gemini_api_key_fn
    app.extensions["persist_gemini_api_key_fn"] = persist_gemini_api_key_fn
    app.extensions["clear_gemini_api_key_fn"] = clear_gemini_api_key_fn
    app.extensions["gemini_api_key_store_available_fn"] = gemini_api_key_store_available_fn
    app.extensions["gemini_api_key_store_mode_fn"] = gemini_api_key_store_mode_fn
    app.extensions["gemini_api_key_store_uses_alt_fallback_fn"] = gemini_api_key_store_uses_alt_fallback_fn
    register_routes(app, build_handler_deps)

    @app.cli.command("db-upgrade")
    def db_upgrade_command() -> None:
        with app.app_context():
            applied = run_migrations_fn()
        if not applied:
            click.echo("Database is up to date.")
            return
        click.echo("Applied migrations:")
        for version in applied:
            click.echo(f"- {version}")

    @app.cli.command("db-status")
    def db_status_command() -> None:
        with app.app_context():
            known = list_known_migrations_fn()
            applied = list_applied_migrations_fn()
            pending = list_pending_migrations_fn()
        click.echo(f"Known migrations: {len(known)}")
        click.echo(f"Applied migrations: {len(applied)}")
        click.echo(f"Pending migrations: {len(pending)}")
        if pending:
            click.echo("Pending versions:")
            for version in pending:
                click.echo(f"- {version}")

    @app.cli.command("db-history")
    def db_history_command() -> None:
        with app.app_context():
            applied = list_applied_migrations_fn()
        if not applied:
            click.echo("No migrations have been applied.")
            return
        click.echo("Applied migration history:")
        for version, applied_at in applied:
            click.echo(f"- {version} @ {applied_at}")

    return app
