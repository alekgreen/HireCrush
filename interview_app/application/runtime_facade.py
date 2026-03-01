from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeCallables:
    get_gemini_generate_json: Callable[[], Callable[..., Any]]
    get_normalize_audio_mime_type: Callable[[], Callable[[str], str | None]]
    get_call_gemini_for_questions: Callable[[], Callable[..., list[str]]]
    get_call_gemini_for_answer: Callable[[], Callable[..., str]]


class RuntimeFacade:
    def __init__(
        self,
        *,
        app,
        os_getenv: Callable[..., str | None],
        requests_module,
        gemini_service_module,
        generation_service_module,
        question_service_module,
        review_service_module,
        parse_json_from_text_fn,
        parse_gemini_questions_fn,
        get_db_fn,
        get_generation_context_questions_fn,
        get_question_by_id_fn,
        clean_question_text_fn,
        question_hash_fn,
        now_utc_fn,
        iso_fn,
        gemini_model_fallbacks: list[str],
        questions_json_schema: dict,
        answer_json_schema: dict,
        feedback_json_schema: dict,
        default_topic_tag_color_code: str,
        max_inline_audio_bytes: int,
        runtime_callables: RuntimeCallables,
    ):
        self._app = app
        self._os_getenv = os_getenv
        self._requests = requests_module
        self._gemini_service = gemini_service_module
        self._generation_service = generation_service_module
        self._question_service = question_service_module
        self._review_service = review_service_module
        self._parse_json_from_text_fn = parse_json_from_text_fn
        self._parse_gemini_questions_fn = parse_gemini_questions_fn
        self._get_db_fn = get_db_fn
        self._get_generation_context_questions_fn = get_generation_context_questions_fn
        self._get_question_by_id_fn = get_question_by_id_fn
        self._clean_question_text_fn = clean_question_text_fn
        self._question_hash_fn = question_hash_fn
        self._now_utc_fn = now_utc_fn
        self._iso_fn = iso_fn
        self._gemini_model_fallbacks = gemini_model_fallbacks
        self._questions_json_schema = questions_json_schema
        self._answer_json_schema = answer_json_schema
        self._feedback_json_schema = feedback_json_schema
        self._default_topic_tag_color_code = default_topic_tag_color_code
        self._max_inline_audio_bytes = max_inline_audio_bytes
        self._runtime_callables = runtime_callables

    def gemini_model_candidates(self) -> list[str]:
        return self._gemini_service.build_model_candidates(
            configured_model=str(self._app.config.get("GEMINI_MODEL", "")),
            env_fallback_models=self._os_getenv("GEMINI_FALLBACK_MODELS", "") or "",
            default_models=self._gemini_model_fallbacks,
        )

    def gemini_generate_json(self, prompt: str, response_schema: dict, temperature: float = 0.8):
        parsed, model = self._gemini_service.generate_json(
            prompt=prompt,
            response_schema=response_schema,
            temperature=temperature,
            api_key=self._app.config["GEMINI_API_KEY"],
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
            api_key=self._app.config["GEMINI_API_KEY"],
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
        )

    def call_gemini_for_answer(self, question: str, topic: str | None = None) -> str:
        return self._generation_service.call_for_answer(
            question=question,
            topic=topic,
            generate_json_fn=self._runtime_callables.get_gemini_generate_json(),
            answer_json_schema=self._answer_json_schema,
        )

    def call_gemini_for_feedback(self, question: str, reference_answer: str, user_answer: str) -> dict:
        return self._generation_service.call_for_feedback(
            question=question,
            reference_answer=reference_answer,
            user_answer=user_answer,
            generate_json_fn=self._runtime_callables.get_gemini_generate_json(),
            feedback_json_schema=self._feedback_json_schema,
        )

    def add_questions(
        self,
        topic: str,
        requested_count: int,
        language: str = "English",
        additional_context: str | None = None,
        topic_color: str = "",
    ) -> tuple[int, int]:
        resolved_topic_color = topic_color or self._default_topic_tag_color_code
        return self._question_service.add_questions(
            topic=topic,
            requested_count=requested_count,
            language=language,
            additional_context=additional_context,
            topic_color=resolved_topic_color,
            get_db_fn=self._get_db_fn,
            get_generation_context_questions_fn=self._get_generation_context_questions_fn,
            call_gemini_for_questions_fn=self._runtime_callables.get_call_gemini_for_questions(),
            clean_question_text_fn=self._clean_question_text_fn,
            question_hash_fn=self._question_hash_fn,
            now_utc_fn=self._now_utc_fn,
            iso_fn=self._iso_fn,
            auto_generate_answers=bool(self._app.config.get("AUTO_GENERATE_ANSWERS", True)),
            call_gemini_for_answer_fn=self._runtime_callables.get_call_gemini_for_answer(),
        )

    def generate_answer_for_question(self, question_id: int) -> str:
        return self._question_service.generate_answer_for_question(
            question_id=question_id,
            get_db_fn=self._get_db_fn,
            get_question_by_id_fn=self._get_question_by_id_fn,
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

    def normalize_topic_filters(self, raw_values: list[str]) -> list[str]:
        return self._review_service.normalize_topic_filters(raw_values)

    def is_randomized_review(self, value: str) -> bool:
        return self._review_service.is_randomized_review(value)

    def extract_review_filters_from_referrer(self, referrer: str) -> tuple[list[str], bool]:
        return self._review_service.extract_review_filters_from_referrer(referrer)

    def review_redirect(
        self,
        *,
        topics: list[str] | None,
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
        return redirect_fn(url_for_fn("review", **params))
