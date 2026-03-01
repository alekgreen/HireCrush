import io
from urllib.parse import parse_qs, urlparse

from app import app as flask_app
from interview_app.db import get_db
from interview_app.repository import get_question_by_id, save_feedback
from interview_app.services import question_service

from tests.support import insert_question


def test_review_submit_good_updates_question(client):
    question_id = insert_question("How does CAP theorem apply in distributed systems?")

    response = client.post(
        f"/review/{question_id}",
        data={"grade": "good"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with flask_app.app_context():
        row = get_db().execute(
            "SELECT repetitions, interval_days FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()

    assert row["repetitions"] == 1
    assert row["interval_days"] == 1


def test_review_route_filters_due_question_by_selected_topics(client):
    insert_question("Explain Python's GIL.", topic="python")
    insert_question("What is a SQL index?", topic="sql")

    res = client.get("/review?topics=python")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Explain Python&#39;s GIL." in body
    assert "What is a SQL index?" not in body


def test_review_route_passes_randomize_and_topics_to_selector(client, override_handler_deps):
    captured = {}

    def fake_get_due_question(topics=None, randomize=False, exclude_question_id=None):
        captured["topics"] = topics
        captured["randomize"] = randomize
        captured["exclude_question_id"] = exclude_question_id
        return None

    override_handler_deps(
        review={
            "get_due_question_fn": fake_get_due_question,
            "get_next_upcoming_fn": lambda topics=None: None,
        }
    )

    res = client.get("/review?topics=python&topics=sql&randomize=1")

    assert res.status_code == 200
    assert captured == {
        "topics": ["python", "sql"],
        "randomize": True,
        "exclude_question_id": None,
    }


def test_review_submit_redirect_preserves_filters(client):
    question_id = insert_question("How does CAP theorem apply in distributed systems?")

    response = client.post(
        f"/review/{question_id}",
        data={"grade": "good", "topics": ["python", "sql"], "randomize": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/review"
    assert query.get("topics") == ["python", "sql"]
    assert query.get("randomize") == ["1"]


def test_review_answer_redirect_preserves_filters(client, override_handler_deps):
    question_id = insert_question("Explain eventual consistency.")
    override_handler_deps(
        review={
            "generate_answer_for_question_fn": lambda _qid: (
                "Eventual consistency means replicas converge over time."
            )
        }
    )

    response = client.post(
        f"/review/{question_id}/answer",
        data={"topics": ["distributed systems"], "randomize": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/review"
    assert query.get("qid") == [str(question_id)]
    assert query.get("topics") == ["distributed systems"]
    assert query.get("randomize") == ["1"]


def test_review_skip_redirect_preserves_filters(client):
    question_id = insert_question("Explain read replicas.")

    response = client.post(
        f"/review/{question_id}/skip",
        data={"topics": ["python", "sql"], "randomize": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    parsed = urlparse(response.headers["Location"])
    query = parse_qs(parsed.query)
    assert parsed.path == "/review"
    assert query.get("skip_qid") == [str(question_id)]
    assert query.get("topics") == ["python", "sql"]
    assert query.get("randomize") == ["1"]


def test_review_route_skip_qid_loads_another_due_question(client):
    first_id = insert_question("Question one?", topic="python")
    insert_question("Question two?", topic="python")

    res = client.get(f"/review?topics=python&skip_qid={first_id}")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Question two?" in body
    assert "Question one?" not in body


def test_review_answer_route_generates_model_answer(client, override_handler_deps):
    question_id = insert_question("Explain eventual consistency.")

    def fake_generate_answer_for_question(question_id_value):
        return question_service.generate_answer_for_question(
            question_id=question_id_value,
            get_db_fn=get_db,
            get_question_by_id_fn=get_question_by_id,
            call_gemini_for_answer_fn=lambda _question, _topic=None: (
                "Eventual consistency means replicas converge over time."
            ),
        )

    override_handler_deps(
        review={"generate_answer_for_question_fn": fake_generate_answer_for_question}
    )
    res = client.post(f"/review/{question_id}/answer", follow_redirects=True)
    assert res.status_code == 200

    with flask_app.app_context():
        row = get_db().execute(
            "SELECT suggested_answer FROM questions WHERE id = ?",
            (question_id,),
        ).fetchone()

    assert "replicas converge over time" in row["suggested_answer"]


def test_review_feedback_route_stores_feedback(client, override_handler_deps):
    question_id = insert_question(
        "What is a database transaction?",
        suggested_answer="A transaction is an ACID unit of work.",
    )
    override_handler_deps(
        review={
            "call_gemini_for_feedback_fn": lambda **_kwargs: {
                "score": 7,
                "feedback": "Good start, add isolation and rollback details.",
                "improved_answer": "A transaction groups operations atomically with ACID guarantees.",
                "strengths": ["Mentioned ACID"],
                "gaps": ["No practical example"],
            }
        }
    )

    res = client.post(
        f"/review/{question_id}/feedback",
        data={"user_answer": "A transaction is one logical unit of work in a DB."},
        follow_redirects=True,
    )
    assert res.status_code == 200

    with flask_app.app_context():
        row = get_db().execute(
            "SELECT score, feedback, improved_answer FROM review_feedback WHERE question_id = ?",
            (question_id,),
        ).fetchone()

    assert row["score"] == 7
    assert "Good start" in row["feedback"]
    assert "ACID guarantees" in row["improved_answer"]


def test_review_route_hides_latest_feedback_by_default(client):
    question_id = insert_question(
        "How does transaction isolation work?",
        suggested_answer="Isolation keeps concurrent transactions from interfering.",
    )
    with flask_app.app_context():
        save_feedback(
            question_id,
            "It prevents concurrency bugs.",
            {
                "score": 6,
                "feedback": "Decent answer, add concrete isolation levels.",
                "improved_answer": "Isolation controls visibility between concurrent transactions.",
                "strengths": ["Mentions concurrency"],
                "gaps": ["No isolation level examples"],
            },
        )

    res = client.get(f"/review?qid={question_id}")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Latest Feedback" not in body
    assert "Decent answer, add concrete isolation levels." not in body
    assert "Submit your answer to generate structured feedback and an improved response." in body


def test_review_route_shows_latest_feedback_with_flag(client):
    question_id = insert_question(
        "What is optimistic locking?",
        suggested_answer="Optimistic locking checks version conflicts at write time.",
    )
    with flask_app.app_context():
        save_feedback(
            question_id,
            "It uses a version field to detect conflicts.",
            {
                "score": 8,
                "feedback": "Good explanation with correct conflict detection idea.",
                "improved_answer": "Optimistic locking detects write conflicts by comparing versions.",
                "strengths": ["Version check noted"],
                "gaps": [],
            },
        )

    res = client.get(f"/review?qid={question_id}&show_feedback=1")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Latest Feedback" in body
    assert "Good explanation with correct conflict detection idea." in body


def test_review_feedback_redirect_includes_show_feedback_flag(client, override_handler_deps):
    question_id = insert_question(
        "Why use indexes in databases?",
        suggested_answer="Indexes speed reads by reducing scanned rows.",
    )
    override_handler_deps(
        review={
            "call_gemini_for_feedback_fn": lambda **_kwargs: {
                "score": 7,
                "feedback": "Solid base answer.",
                "improved_answer": "Indexes accelerate lookups by narrowing search paths.",
                "strengths": [],
                "gaps": [],
            }
        }
    )

    res = client.post(
        f"/review/{question_id}/feedback",
        data={"user_answer": "Indexes can make queries faster by avoiding full scans."},
        follow_redirects=False,
    )

    assert res.status_code == 302
    assert f"/review?qid={question_id}&show_feedback=1" in res.headers["Location"]


def test_review_transcribe_route_returns_json_transcript(client, override_handler_deps):
    override_handler_deps(
        review={
            "call_gemini_for_transcription_fn": lambda _audio_bytes, _mime_type: (
                "Transcribed answer text."
            )
        }
    )

    res = client.post(
        "/review/transcribe",
        data={"audio": (io.BytesIO(b"RIFFfake"), "answer.wav", "audio/wav")},
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload["transcript"] == "Transcribed answer text."


def test_review_transcribe_route_requires_audio_file(client):
    res = client.post("/review/transcribe", data={})

    assert res.status_code == 400
    payload = res.get_json()
    assert "Audio file is required." in payload["error"]


def test_review_transcribe_route_rejects_unsupported_format(client):
    res = client.post(
        "/review/transcribe",
        data={"audio": (io.BytesIO(b"fake"), "answer.bin", "application/octet-stream")},
    )

    assert res.status_code == 400
    payload = res.get_json()
    assert "Unsupported audio format." in payload["error"]
