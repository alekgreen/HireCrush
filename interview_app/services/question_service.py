def add_questions(
    topic: str,
    subtopic: str | None,
    requested_count: int,
    language: str,
    additional_context: str | None,
    topic_color: str,
    get_db_fn,
    get_generation_context_questions_fn,
    call_gemini_for_questions_fn,
    clean_question_text_fn,
    question_hash_fn,
    now_utc_fn,
    iso_fn,
    auto_generate_answers: bool,
    call_gemini_for_answer_fn,
    progress_callback=None,
) -> tuple[int, int]:
    db = get_db_fn()
    existing_hashes = {
        row["text_hash"] for row in db.execute("SELECT text_hash FROM questions").fetchall()
    }

    inserted = 0
    attempts = 0
    # Generate one-by-one to improve per-question quality and context adaptation.
    max_attempts = max(6, requested_count * 4)
    try:
        generation_context = get_generation_context_questions_fn(topic, subtopic=subtopic, limit=120)
    except TypeError:
        generation_context = get_generation_context_questions_fn(topic, limit=120)
    if progress_callback is not None:
        try:
            progress_callback(inserted, requested_count)
        except Exception:
            pass

    while inserted < requested_count and attempts < max_attempts:
        attempts += 1
        needed = 1
        call_kwargs = {
            "language": language,
            "existing_questions": generation_context,
            "additional_context": additional_context,
        }
        if subtopic:
            call_kwargs["subtopic"] = subtopic
        try:
            generated = call_gemini_for_questions_fn(
                topic,
                needed,
                **call_kwargs,
            )
        except TypeError:
            call_kwargs.pop("subtopic", None)
            generated = call_gemini_for_questions_fn(
                topic,
                needed,
                **call_kwargs,
            )
        if not generated:
            continue

        for item in generated:
            if inserted >= requested_count:
                break
            text = clean_question_text_fn(item)
            if not text or len(text) < 10:
                continue
            text_hash = question_hash_fn(text)
            if text_hash in existing_hashes:
                continue

            now = now_utc_fn()
            suggested_answer = None
            if auto_generate_answers:
                try:
                    suggested_answer = call_gemini_for_answer_fn(text, topic)
                except Exception:
                    suggested_answer = None

            db.execute(
                """
                INSERT INTO questions (
                    text, text_hash, topic, subtopic, topic_color, subtopic_color, created_at, next_review_at,
                    suggested_answer, repetitions, interval_days, ease_factor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 2.5)
                """,
                (
                    text,
                    text_hash,
                    topic,
                    subtopic,
                    topic_color,
                    topic_color if subtopic else None,
                    iso_fn(now),
                    iso_fn(now),
                    suggested_answer,
                ),
            )
            existing_hashes.add(text_hash)
            generation_context.append(text)
            inserted += 1
            if progress_callback is not None:
                try:
                    progress_callback(inserted, requested_count)
                except Exception:
                    pass

    db.commit()
    if progress_callback is not None:
        try:
            progress_callback(inserted, requested_count)
        except Exception:
            pass
    return inserted, requested_count - inserted


def add_code_review_questions(
    topic: str,
    subtopic: str | None,
    requested_count: int,
    language: str,
    additional_context: str | None,
    topic_color: str,
    get_db_fn,
    get_generation_context_questions_fn,
    call_gemini_for_code_review_questions_fn,
    clean_question_text_fn,
    question_hash_fn,
    now_utc_fn,
    iso_fn,
    progress_callback=None,
) -> tuple[int, int]:
    db = get_db_fn()
    existing_hashes = {
        row["text_hash"] for row in db.execute("SELECT text_hash FROM questions").fetchall()
    }
    existing_texts = [
        row["text"]
        for row in db.execute(
            "SELECT text FROM questions WHERE question_type = 'code_review' ORDER BY created_at DESC LIMIT 80"
        ).fetchall()
    ]

    inserted = 0
    attempts = 0
    # Generate one-by-one to improve per-question quality and context adaptation.
    max_attempts = max(6, requested_count * 4)
    if progress_callback is not None:
        try:
            progress_callback(inserted, requested_count)
        except Exception:
            pass

    while inserted < requested_count and attempts < max_attempts:
        attempts += 1
        needed = 1
        call_kwargs = {
            "language": language,
            "existing_questions": existing_texts,
            "additional_context": additional_context,
        }
        if subtopic:
            call_kwargs["subtopic"] = subtopic
        try:
            generated = call_gemini_for_code_review_questions_fn(topic, needed, **call_kwargs)
        except TypeError:
            call_kwargs.pop("subtopic", None)
            generated = call_gemini_for_code_review_questions_fn(topic, needed, **call_kwargs)
        if not generated:
            continue

        for item in generated:
            if inserted >= requested_count:
                break
            if not isinstance(item, dict):
                continue
            question_text = clean_question_text_fn(item.get("question_text", ""))
            code_snippet = str(item.get("code_snippet", "")).strip()
            code_language = str(item.get("language", "")).strip().lower()
            if not question_text or len(question_text) < 10 or not code_snippet:
                continue
            text_hash = question_hash_fn(question_text)
            if text_hash in existing_hashes:
                continue

            now = now_utc_fn()
            db.execute(
                """
                INSERT INTO questions (
                    text, text_hash, topic, subtopic, topic_color, subtopic_color, created_at, next_review_at,
                    suggested_answer, repetitions, interval_days, ease_factor,
                    question_type, code_snippet, code_language
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, 0, 0, 2.5, 'code_review', ?, ?)
                """,
                (
                    question_text,
                    text_hash,
                    topic,
                    subtopic,
                    topic_color,
                    topic_color if subtopic else None,
                    iso_fn(now),
                    iso_fn(now),
                    code_snippet,
                    code_language,
                ),
            )
            existing_hashes.add(text_hash)
            existing_texts.append(question_text)
            inserted += 1
            if progress_callback is not None:
                try:
                    progress_callback(inserted, requested_count)
                except Exception:
                    pass

    db.commit()
    if progress_callback is not None:
        try:
            progress_callback(inserted, requested_count)
        except Exception:
            pass
    return inserted, requested_count - inserted


def generate_answer_for_question(
    question_id: int,
    get_db_fn,
    get_question_by_id_fn,
    call_gemini_for_answer_fn,
) -> str:
    db = get_db_fn()
    question = get_question_by_id_fn(question_id)
    if question is None:
        raise RuntimeError("Question not found.")

    existing = (question["suggested_answer"] or "").strip()
    if existing:
        return existing

    question_type = (question["question_type"] or "theory") if "question_type" in question.keys() else "theory"
    if question_type == "code_review":
        code_snippet = (question["code_snippet"] or "") if "code_snippet" in question.keys() else ""
        code_language = (question["code_language"] or "") if "code_language" in question.keys() else ""
        code_block = f"\n\nOriginal code ({code_language or 'unknown'}):\n{code_snippet}" if code_snippet else ""
        question_text = question["text"] + code_block
    else:
        question_text = question["text"]

    answer = call_gemini_for_answer_fn(question_text, question["topic"])
    db.execute(
        "UPDATE questions SET suggested_answer = ? WHERE id = ?",
        (answer, question_id),
    )
    db.commit()
    return answer


def format_http_error(exc) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return "Gemini API request failed."

    status = response.status_code
    reason = response.reason or "Error"
    if status == 404:
        return (
            "Gemini model was not found. Set GEMINI_MODEL to a supported model "
            "(for example: gemini-2.5-flash or gemini-3-flash-preview)."
        )
    if status == 429:
        return "Gemini API rate limit exceeded. Please retry in a moment."
    return f"Gemini API request failed ({status} {reason})."
