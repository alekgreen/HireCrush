from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from interview_app.application.ports.repositories import QuestionRepository


@dataclass(frozen=True)
class RuntimeCallables:
    get_gemini_generate_json: Callable[[], Callable[..., Any]]
    get_normalize_audio_mime_type: Callable[[], Callable[[str], str | None]]
    get_call_gemini_for_questions: Callable[[], Callable[..., list[str]]]
    get_call_gemini_for_answer: Callable[[], Callable[..., str]]
    get_call_gemini_for_code_review_questions: Callable[[], Callable[..., list[dict]]]


@dataclass(frozen=True)
class RuntimeInfraDeps:
    os_getenv: Callable[..., str | None]
    requests_module: Any
    get_db_fn: Callable[..., Any]


@dataclass(frozen=True)
class RuntimeServiceModules:
    gemini_service_module: Any
    generation_service_module: Any
    question_service_module: Any
    review_service_module: Any


@dataclass(frozen=True)
class RuntimeParserDeps:
    parse_json_from_text_fn: Callable[..., Any]
    parse_gemini_questions_fn: Callable[..., list[str]]


@dataclass(frozen=True)
class RuntimeRepositoryDeps:
    question_repository: QuestionRepository


@dataclass(frozen=True)
class RuntimeUtilityDeps:
    clean_question_text_fn: Callable[..., str]
    question_hash_fn: Callable[..., str]
    now_utc_fn: Callable[..., Any]
    iso_fn: Callable[..., str]


@dataclass(frozen=True)
class RuntimeConfigDeps:
    gemini_model_fallbacks: list[str]
    questions_json_schema: dict
    answer_json_schema: dict
    feedback_json_schema: dict
    code_review_question_schema: dict
    default_topic_tag_color_code: str
    max_inline_audio_bytes: int


@dataclass(frozen=True)
class RuntimeDependencies:
    infra: RuntimeInfraDeps
    modules: RuntimeServiceModules
    parsers: RuntimeParserDeps
    repositories: RuntimeRepositoryDeps
    utils: RuntimeUtilityDeps
    config: RuntimeConfigDeps


class RuntimeFacade:
    def __init__(
        self,
        *,
        app,
        deps: RuntimeDependencies,
        runtime_callables: RuntimeCallables,
    ):
        self._app = app
        self._os_getenv = deps.infra.os_getenv
        self._requests = deps.infra.requests_module
        self._get_db_fn = deps.infra.get_db_fn

        self._gemini_service = deps.modules.gemini_service_module
        self._generation_service = deps.modules.generation_service_module
        self._question_service = deps.modules.question_service_module
        self._review_service = deps.modules.review_service_module

        self._parse_json_from_text_fn = deps.parsers.parse_json_from_text_fn
        self._parse_gemini_questions_fn = deps.parsers.parse_gemini_questions_fn

        self._question_repository = deps.repositories.question_repository

        self._clean_question_text_fn = deps.utils.clean_question_text_fn
        self._question_hash_fn = deps.utils.question_hash_fn
        self._now_utc_fn = deps.utils.now_utc_fn
        self._iso_fn = deps.utils.iso_fn

        self._gemini_model_fallbacks = deps.config.gemini_model_fallbacks
        self._questions_json_schema = deps.config.questions_json_schema
        self._answer_json_schema = deps.config.answer_json_schema
        self._feedback_json_schema = deps.config.feedback_json_schema
        self._code_review_question_schema = deps.config.code_review_question_schema
        self._default_topic_tag_color_code = deps.config.default_topic_tag_color_code
        self._max_inline_audio_bytes = deps.config.max_inline_audio_bytes
        self._runtime_callables = runtime_callables

    def _resolved_gemini_model(self) -> str:
        resolver = self._app.extensions.get("resolve_gemini_model_fn")
        if callable(resolver):
            try:
                resolved = str(resolver() or "").strip()
                if resolved:
                    return resolved
            except RuntimeError:
                pass
        return str(self._app.config.get("GEMINI_MODEL", "")).strip()

    def _resolved_gemini_api_key(self) -> str:
        resolver = self._app.extensions.get("resolve_gemini_api_key_fn")
        if callable(resolver):
            try:
                resolved = str(resolver() or "").strip()
                if resolved:
                    return resolved
            except RuntimeError:
                pass
        return str(self._app.config.get("GEMINI_API_KEY", "")).strip()

    def gemini_model_candidates(self) -> list[str]:
        return self._gemini_service.build_model_candidates(
            configured_model=self._resolved_gemini_model(),
            env_fallback_models=self._os_getenv("GEMINI_FALLBACK_MODELS", "") or "",
            default_models=self._gemini_model_fallbacks,
        )

    def gemini_generate_json(self, prompt: str, response_schema: dict, temperature: float = 0.8):
        parsed, model = self._gemini_service.generate_json(
            prompt=prompt,
            response_schema=response_schema,
            temperature=temperature,
            api_key=self._resolved_gemini_api_key(),
            model_candidates=self.gemini_model_candidates(),
            parse_json_from_text_fn=self._parse_json_from_text_fn,
            http_client=self._requests,
        )
        self._app.config["LAST_WORKING_GEMINI_MODEL"] = model
        return parsed

    def normalize_audio_mime_type(self, mime_type: str) -> str | None:
        return self._gemini_service.normalize_audio_mime_type(mime_type)

    def call_gemini_for_transcription(self, audio_bytes: bytes, mime_type: str) -> str:
        transcript, model = self._gemini_service.transcribe_audio(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            api_key=self._resolved_gemini_api_key(),
            model_candidates=self.gemini_model_candidates(),
            http_client=self._requests,
            normalize_audio_mime_type_fn=self._runtime_callables.get_normalize_audio_mime_type(),
            max_inline_audio_bytes=self._max_inline_audio_bytes,
        )
        self._app.config["LAST_WORKING_GEMINI_MODEL"] = model
        return transcript

    def call_gemini_for_questions(
        self,
        topic: str,
        count: int,
        language: str = "English",
        existing_questions: list[str] | None = None,
        additional_context: str | None = None,
        subtopic: str | None = None,
    ) -> list[str]:
        return self._generation_service.call_for_questions(
            topic=topic,
            count=count,
            language=language,
            existing_questions=existing_questions,
            additional_context=additional_context,
            generate_json_fn=self._runtime_callables.get_gemini_generate_json(),
            questions_json_schema=self._questions_json_schema,
            parse_gemini_questions_fn=self._parse_gemini_questions_fn,
            subtopic=subtopic,
        )

    def call_gemini_for_answer(self, question: str, topic: str | None = None) -> str:
        return self._generation_service.call_for_answer(
            question=question,
            topic=topic,
            generate_json_fn=self._runtime_callables.get_gemini_generate_json(),
            answer_json_schema=self._answer_json_schema,
        )

    def stream_answer_for_question(self, question_id: int):
        db = self._get_db_fn()
        question = self._question_repository.get_question_by_id(question_id)
        if question is None:
            raise RuntimeError("Question not found.")

        existing = (question["suggested_answer"] or "").strip()
        if existing:
            yield existing
            return

        question_text, question_topic = self._question_service.build_answer_generation_input(question)
        prompt = self._generation_service.build_answer_prompt(question=question_text, topic=question_topic)
        stream, model = self._gemini_service.stream_text(
            prompt=prompt,
            temperature=0.6,
            api_key=self._resolved_gemini_api_key(),
            model_candidates=self.gemini_model_candidates(),
            http_client=self._requests,
        )

        chunks: list[str] = []
        for piece in stream:
            if not piece:
                continue
            chunks.append(piece)
            yield piece

        answer = "".join(chunks).strip()
        if not answer:
            raise RuntimeError("Gemini did not return a valid answer.")

        db.execute(
            "UPDATE questions SET suggested_answer = ? WHERE id = ?",
            (answer, question_id),
        )
        db.commit()
        self._app.config["LAST_WORKING_GEMINI_MODEL"] = model

    def call_gemini_for_feedback(self, question: str, reference_answer: str, user_answer: str) -> dict:
        return self._generation_service.call_for_feedback(
            question=question,
            reference_answer=reference_answer,
            user_answer=user_answer,
            generate_json_fn=self._runtime_callables.get_gemini_generate_json(),
            feedback_json_schema=self._feedback_json_schema,
        )

    def call_gemini_for_code_review_questions(
        self,
        topic: str,
        count: int,
        language: str = "English",
        existing_questions: list[str] | None = None,
        additional_context: str | None = None,
        subtopic: str | None = None,
    ) -> list[dict]:
        return self._generation_service.call_for_code_review_questions(
            topic=topic,
            count=count,
            language=language,
            existing_questions=existing_questions,
            additional_context=additional_context,
            generate_json_fn=self._runtime_callables.get_gemini_generate_json(),
            code_review_question_schema=self._code_review_question_schema,
            subtopic=subtopic,
        )

    def call_gemini_for_code_review_feedback(
        self,
        question_text: str,
        original_code: str,
        user_code: str,
        language: str,
    ) -> dict:
        return self._generation_service.call_for_code_review_feedback(
            question_text=question_text,
            original_code=original_code,
            user_code=user_code,
            language=language,
            generate_json_fn=self._runtime_callables.get_gemini_generate_json(),
            feedback_json_schema=self._feedback_json_schema,
        )

    def add_code_review_questions(
        self,
        topic: str,
        requested_count: int,
        language: str = "English",
        additional_context: str | None = None,
        topic_color: str = "",
        subtopic: str | None = None,
        progress_callback=None,
    ) -> tuple[int, int]:
        resolved_topic_color = topic_color or self._default_topic_tag_color_code
        return self._question_service.add_code_review_questions(
            topic=topic,
            subtopic=subtopic,
            requested_count=requested_count,
            language=language,
            additional_context=additional_context,
            topic_color=resolved_topic_color,
            get_db_fn=self._get_db_fn,
            get_generation_context_questions_fn=self._question_repository.get_generation_context_questions,
            call_gemini_for_code_review_questions_fn=self._runtime_callables.get_call_gemini_for_code_review_questions(),
            clean_question_text_fn=self._clean_question_text_fn,
            question_hash_fn=self._question_hash_fn,
            now_utc_fn=self._now_utc_fn,
            iso_fn=self._iso_fn,
            progress_callback=progress_callback,
        )

    def add_questions(
        self,
        topic: str,
        requested_count: int,
        language: str = "English",
        additional_context: str | None = None,
        topic_color: str = "",
        subtopic: str | None = None,
        progress_callback=None,
    ) -> tuple[int, int]:
        resolved_topic_color = topic_color or self._default_topic_tag_color_code
        return self._question_service.add_questions(
            topic=topic,
            subtopic=subtopic,
            requested_count=requested_count,
            language=language,
            additional_context=additional_context,
            topic_color=resolved_topic_color,
            get_db_fn=self._get_db_fn,
            get_generation_context_questions_fn=self._question_repository.get_generation_context_questions,
            call_gemini_for_questions_fn=self._runtime_callables.get_call_gemini_for_questions(),
            clean_question_text_fn=self._clean_question_text_fn,
            question_hash_fn=self._question_hash_fn,
            now_utc_fn=self._now_utc_fn,
            iso_fn=self._iso_fn,
            auto_generate_answers=bool(self._app.config.get("AUTO_GENERATE_ANSWERS", True)),
            call_gemini_for_answer_fn=self._runtime_callables.get_call_gemini_for_answer(),
            progress_callback=progress_callback,
        )

    def generate_answer_for_question(self, question_id: int) -> str:
        return self._question_service.generate_answer_for_question(
            question_id=question_id,
            get_db_fn=self._get_db_fn,
            get_question_by_id_fn=self._question_repository.get_question_by_id,
            call_gemini_for_answer_fn=self._runtime_callables.get_call_gemini_for_answer(),
        )

    def format_http_error(self, exc) -> str:
        return self._question_service.format_http_error(exc)

    def apply_review(self, question_id: int, rating: int) -> None:
        self._review_service.apply_review(
            question_id=question_id,
            rating=rating,
            get_db_fn=self._get_db_fn,
            now_utc_fn=self._now_utc_fn,
            iso_fn=self._iso_fn,
        )

    def get_review_reappearance_labels(self, question) -> dict[str, str]:
        return self._review_service.get_review_reappearance_labels(
            question=question,
            now_utc_fn=self._now_utc_fn,
        )

    def normalize_topic_filters(self, raw_values: list[str]) -> list[str]:
        return self._review_service.normalize_topic_filters(raw_values)

    def normalize_subtopic_filters(self, raw_values: list[str]) -> list[tuple[str, str]]:
        return self._review_service.normalize_subtopic_filters(raw_values)

    def serialize_topic_subtopic_filter(self, topic: str, subtopic: str) -> str:
        return self._review_service.serialize_topic_subtopic_filter(topic, subtopic)

    def is_randomized_review(self, value: str) -> bool:
        return self._review_service.is_randomized_review(value)

    def extract_review_filters_from_referrer(
        self,
        referrer: str,
    ) -> tuple[list[str], list[tuple[str, str]], bool]:
        return self._review_service.extract_review_filters_from_referrer(referrer)

    def review_redirect(
        self,
        *,
        topics: list[str] | None,
        subtopics: list[tuple[str, str]] | None,
        randomize: bool,
        qid: int | None,
        show_feedback: bool,
        skip_qid: int | None,
        redirect_fn,
        url_for_fn,
    ):
        params: dict[str, object] = {}
        if qid is not None:
            params["qid"] = qid
        if show_feedback:
            params["show_feedback"] = 1
        if skip_qid is not None:
            params["skip_qid"] = int(skip_qid)
        if randomize:
            params["randomize"] = 1
        if topics:
            params["topics"] = topics
        if subtopics:
            serialized_subtopics: list[str] = []
            for topic, subtopic in subtopics:
                value = self.serialize_topic_subtopic_filter(topic, subtopic)
                if value:
                    serialized_subtopics.append(value)
            if serialized_subtopics:
                params["subtopics"] = serialized_subtopics
        return redirect_fn(url_for_fn("review", **params))
