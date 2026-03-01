import json
import re


def call_for_questions(
    topic: str,
    count: int,
    language: str,
    existing_questions: list[str] | None,
    additional_context: str | None,
    generate_json_fn,
    questions_json_schema: dict,
    parse_gemini_questions_fn,
    subtopic: str | None = None,
) -> list[str]:
    context_block = ""
    if existing_questions:
        capped_lines = []
        total_chars = 0
        max_chars = 12000
        for idx, question in enumerate(existing_questions[:120], start=1):
            compact = re.sub(r"\s+", " ", str(question).strip())
            if not compact:
                continue
            if len(compact) > 220:
                compact = compact[:217] + "..."
            line = f"{idx}. {compact}"
            total_chars += len(line) + 1
            if total_chars > max_chars:
                break
            capped_lines.append(line)
        if capped_lines:
            context_block = (
                "Existing questions already stored in the system:\n"
                + "\n".join(capped_lines)
                + "\n"
            )

    additional_context_block = ""
    if additional_context:
        compact_context = re.sub(r"\s+", " ", str(additional_context).strip())
        if compact_context:
            if len(compact_context) > 1200:
                compact_context = compact_context[:1200].rstrip() + "..."
            additional_context_block = (
                "Additional user context to follow when generating questions:\n"
                f"{compact_context}\n"
            )

    prompt = (
        "Generate interview questions.\n"
        f"Topic: {topic}\n"
        + (f"Subtopic: {subtopic}\n" if subtopic else "")
        + f"Count: {count}\n"
        + f"Language: {language}\n"
        + f"Write every question in {language}.\n"
        + "Do not repeat or paraphrase any existing question with the same intent.\n"
        + "A reworded version of an existing question still counts as duplicate.\n"
        + f"{additional_context_block}"
        + f"{context_block}"
        + "Return concise, unique interview questions only."
    )

    parsed = generate_json_fn(prompt, questions_json_schema, temperature=0.9)
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, dict):
        values = parsed.get("questions", [])
        if isinstance(values, list):
            return [str(item).strip() for item in values if str(item).strip()]
    return parse_gemini_questions_fn(json.dumps(parsed))


def call_for_answer(
    question: str,
    topic: str | None,
    generate_json_fn,
    answer_json_schema: dict,
) -> str:
    prompt = (
        "You are helping a candidate prepare for interviews.\n"
        f"Topic: {topic or 'General'}\n"
        f"Question: {question}\n"
        "Provide one high-quality sample answer (around 120-220 words), practical and specific."
    )
    parsed = generate_json_fn(prompt, answer_json_schema, temperature=0.6)
    if isinstance(parsed, dict):
        answer = str(parsed.get("answer", "")).strip()
        if answer:
            return answer
    raise RuntimeError("Gemini did not return a valid answer.")


def call_for_code_review_questions(
    topic: str,
    count: int,
    language: str,
    existing_questions: list[str] | None,
    additional_context: str | None,
    generate_json_fn,
    code_review_question_schema: dict,
    subtopic: str | None = None,
) -> list[dict]:
    context_block = ""
    if existing_questions:
        capped_lines = []
        total_chars = 0
        max_chars = 8000
        for idx, question in enumerate(existing_questions[:80], start=1):
            compact = re.sub(r"\s+", " ", str(question).strip())
            if not compact:
                continue
            if len(compact) > 160:
                compact = compact[:157] + "..."
            line = f"{idx}. {compact}"
            total_chars += len(line) + 1
            if total_chars > max_chars:
                break
            capped_lines.append(line)
        if capped_lines:
            context_block = (
                "Existing question descriptions already stored (avoid duplicating these):\n"
                + "\n".join(capped_lines)
                + "\n"
            )

    additional_context_block = ""
    if additional_context:
        compact_context = re.sub(r"\s+", " ", str(additional_context).strip())
        if compact_context:
            if len(compact_context) > 1200:
                compact_context = compact_context[:1200].rstrip() + "..."
            additional_context_block = (
                "Additional user context:\n"
                f"{compact_context}\n"
            )

    prompt = (
        "Generate code review challenges for interview practice.\n"
        f"Topic: {topic}\n"
        + (f"Subtopic: {subtopic}\n" if subtopic else "")
        + f"Count: {count}\n"
        + f"Question language: {language}\n"
        + "For each challenge:\n"
        + "- Write a question_text (in the specified language) describing what the candidate must find and fix "
        "(e.g. 'Fix the 2 bugs and add a comment explaining each issue.')\n"
        + "- Write a code_snippet containing realistic, intentional bugs, logic errors, anti-patterns, "
        "or security issues. The code should look plausible but have clear problems.\n"
        + "- Set language to the programming language name (python, javascript, java, go, etc.).\n"
        + "Vary the type of issues: logic errors, off-by-one, null handling, inefficiency, security flaws, etc.\n"
        + "Do not repeat or paraphrase existing question descriptions.\n"
        + f"{additional_context_block}"
        + f"{context_block}"
        + "Return unique, realistic code review challenges only."
    )

    parsed = generate_json_fn(prompt, code_review_question_schema, temperature=0.85)
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def call_for_code_review_feedback(
    question_text: str,
    original_code: str,
    user_code: str,
    language: str,
    generate_json_fn,
    feedback_json_schema: dict,
) -> dict:
    prompt = (
        "Evaluate the candidate's code review submission.\n"
        f"Task: {question_text}\n"
        f"Language: {language or 'unknown'}\n"
        f"Original code (with intentional issues):\n```\n{original_code}\n```\n"
        f"Candidate's modified code:\n```\n{user_code}\n```\n"
        "Assess whether the candidate correctly identified and fixed all issues. "
        "Consider: correctness of fixes, added comments, missed problems, introduced new bugs. "
        "Score 1-10. In improved_answer provide the fully corrected code with explanatory comments."
    )
    parsed = generate_json_fn(prompt, feedback_json_schema, temperature=0.4)
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini did not return a valid feedback payload.")

    def to_list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return {
        "score": max(1, min(10, int(parsed.get("score", 1)))),
        "feedback": str(parsed.get("feedback", "")).strip() or "No feedback provided.",
        "improved_answer": str(parsed.get("improved_answer", "")).strip()
        or "No improved answer provided.",
        "strengths": to_list(parsed.get("strengths")),
        "gaps": to_list(parsed.get("gaps")),
    }


def call_for_feedback(
    question: str,
    reference_answer: str,
    user_answer: str,
    generate_json_fn,
    feedback_json_schema: dict,
) -> dict:
    prompt = (
        "Evaluate the user's interview answer.\n"
        f"Question: {question}\n"
        f"Reference answer: {reference_answer}\n"
        f"User answer: {user_answer}\n"
        "Score the user answer from 1 to 10 and provide direct coaching."
    )
    parsed = generate_json_fn(prompt, feedback_json_schema, temperature=0.4)
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini did not return a valid feedback payload.")

    def to_list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return {
        "score": max(1, min(10, int(parsed.get("score", 1)))),
        "feedback": str(parsed.get("feedback", "")).strip() or "No feedback provided.",
        "improved_answer": str(parsed.get("improved_answer", "")).strip()
        or "No improved answer provided.",
        "strengths": to_list(parsed.get("strengths")),
        "gaps": to_list(parsed.get("gaps")),
    }
