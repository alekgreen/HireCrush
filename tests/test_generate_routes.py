import time

import requests

from interview_app.utils import serialize_topic_subtopic
from tests.support import insert_question


def test_generate_route_success_flash(client, override_handler_deps):
    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        return 2, 1

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={"topic": "system design", "count": "3", "language": "en"},
        follow_redirects=True,
    )

    body = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "Added 2 unique question(s)." in body
    assert "Could not add 1 question(s) after uniqueness checks." in body


def test_generate_route_masks_key_in_http_error(client, override_handler_deps):
    response = requests.Response()
    response.status_code = 404
    response.reason = "Not Found"
    response.url = "https://example.com?key=SUPERSECRET"
    http_err = requests.HTTPError("raw error", response=response)

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        raise http_err

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    res = client.post(
        "/generate",
        data={"topic": "python", "count": "2", "language": "en"},
        follow_redirects=True,
    )

    body = res.data.decode("utf-8")
    assert res.status_code == 200
    assert "Gemini model was not found." in body
    assert "SUPERSECRET" not in body


def test_generate_route_passes_selected_language(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic"] = _topic
        captured["count"] = _count
        captured["language"] = language
        captured["additional_context"] = additional_context
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={"topic": "system design", "count": "2", "language": "es"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured == {
        "topic": "system design",
        "count": 2,
        "language": "Spanish",
        "additional_context": None,
        "topic_color": "blue",
    }


def test_generate_route_uses_selected_existing_topic(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic"] = _topic
        captured["count"] = _count
        captured["language"] = language
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={"topic_select": "python", "count": "2", "language": "en"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured["topic"] == "python"
    assert captured["count"] == 2
    assert captured["topic_color"] == "blue"


def test_generate_route_prefers_custom_topic_over_selected(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic"] = _topic
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={
            "topic_select": "python",
            "topic_new": "distributed systems",
            "count": "2",
            "language": "en",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured["topic"] == "distributed systems"
    assert captured["topic_color"] == "blue"


def test_generate_route_accepts_subtopic_without_explicit_topic(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
        subtopic=None,
    ):
        captured["topic"] = _topic
        captured["count"] = _count
        captured["subtopic"] = subtopic
        captured["language"] = language
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={
            "subtopic_select": serialize_topic_subtopic("DevOps", "Kubernetes"),
            "count": "2",
            "language": "en",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured == {
        "topic": "DevOps",
        "count": 2,
        "subtopic": "Kubernetes",
        "language": "English",
    }


def test_generate_route_rejects_invalid_language(client):
    response = client.post(
        "/generate",
        data={"topic": "python", "count": "2", "language": "xx"},
        follow_redirects=True,
    )

    body = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "Language is invalid." in body


def test_generate_route_passes_optional_context_and_selected_color(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic"] = _topic
        captured["count"] = _count
        captured["language"] = language
        captured["additional_context"] = additional_context
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={
            "topic": "system design",
            "count": "2",
            "language": "en",
            "additional_context": "Staff-level architecture and tradeoffs.",
            "topic_color": "emerald",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured == {
        "topic": "system design",
        "count": 2,
        "language": "English",
        "additional_context": "Staff-level architecture and tradeoffs.",
        "topic_color": "emerald",
    }


def test_generate_route_rejects_invalid_topic_color(client):
    response = client.post(
        "/generate",
        data={
            "topic": "python",
            "count": "2",
            "language": "en",
            "topic_color": "not-a-color",
        },
        follow_redirects=True,
    )

    body = response.data.decode("utf-8")
    assert response.status_code == 200
    assert "Topic tag color is invalid." in body


def test_generate_route_uses_existing_topic_color_when_none_selected(client, override_handler_deps):
    insert_question("What is a queue?", topic="python", topic_color="rose")
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
    ):
        captured["topic_color"] = topic_color
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={"topic_select": "python", "count": "2", "language": "en"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured["topic_color"] == "rose"


def test_generate_page_includes_generation_progress_bar(client):
    response = client.get("/generate")
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert 'id="generation_progress"' in body
    assert 'id="generation_progress_bar"' in body


def test_generate_page_includes_async_generation_urls(client):
    response = client.get("/generate")
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert "data-generate-start-url=" in body
    assert "data-generate-progress-url-template=" in body
    assert "data-generate-scope-preview-url=" in body


def test_generate_page_prefills_topic_and_subtopic_from_query(client):
    insert_question("Explain event loops.", topic="Python", subtopic="AsyncIO")
    response = client.get("/generate?topic=python&subtopic=asyncio")
    body = response.data.decode("utf-8")

    assert response.status_code == 200
    assert 'id="topic"' in body
    assert 'name="topic"' in body
    assert 'value="Python"' in body
    assert 'id="subtopic"' in body
    assert 'name="subtopic"' in body
    assert 'value="AsyncIO"' in body


def test_generate_route_accepts_unified_topic_and_subtopic_inputs(client, override_handler_deps):
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
        subtopic=None,
    ):
        captured["topic"] = _topic
        captured["subtopic"] = subtopic
        captured["count"] = _count
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={
            "topic": "Python",
            "subtopic": "AsyncIO",
            "count": "2",
            "language": "en",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured["topic"] == "Python"
    assert captured["subtopic"] == "AsyncIO"
    assert captured["count"] == 2


def test_generate_route_infers_topic_from_unified_subtopic(client, override_handler_deps):
    insert_question("Describe k8s services.", topic="DevOps", subtopic="Kubernetes")
    captured = {}

    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
        subtopic=None,
    ):
        captured["topic"] = _topic
        captured["subtopic"] = subtopic
        return 1, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    response = client.post(
        "/generate",
        data={
            "subtopic": "Kubernetes",
            "count": "2",
            "language": "en",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert captured["topic"] == "DevOps"
    assert captured["subtopic"] == "Kubernetes"


def test_generate_scope_preview_returns_scope_counts(client):
    insert_question("Explain event loops.", topic="Python", subtopic="AsyncIO", topic_color="amber")
    insert_question("How does await work?", topic="Python", subtopic="AsyncIO")
    insert_question("What is gradual typing?", topic="Python", subtopic="Typing")

    scope_subtopic = serialize_topic_subtopic("Python", "AsyncIO")
    response = client.get(f"/generate/scope-preview?topic=python&subtopic={scope_subtopic}")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["topic"] == "Python"
    assert payload["subtopic"] == "AsyncIO"
    assert payload["topic_exists"] is True
    assert payload["subtopic_exists"] is True
    assert payload["topic_total_questions"] == 3
    assert payload["subtopic_total_questions"] == 2
    assert payload["recommended_count"] == 4
    assert payload["resolved_topic_color"] == "amber"
    assert payload["warnings"] == []


def test_generate_scope_preview_infers_topic_from_plain_subtopic(client):
    insert_question("Describe k8s services.", topic="DevOps", subtopic="Kubernetes")
    response = client.get("/generate/scope-preview?subtopic=Kubernetes")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["topic"] == "DevOps"
    assert payload["subtopic"] == "Kubernetes"
    assert "Topic was inferred from the selected subtopic." in payload["warnings"]


def test_generate_scope_preview_rejects_mismatched_topic_and_subtopic(client):
    mismatched = serialize_topic_subtopic("DevOps", "Kubernetes")
    response = client.get(f"/generate/scope-preview?topic=python&subtopic={mismatched}")
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "Selected subtopic does not belong to the chosen topic."


def test_generate_start_and_progress_report_done_count(client, override_handler_deps):
    def fake_add_questions(
        _topic,
        _count,
        language="English",
        additional_context=None,
        topic_color="blue",
        progress_callback=None,
    ):
        if progress_callback is not None:
            progress_callback(0, _count)
            progress_callback(1, _count)
            progress_callback(2, _count)
        return 2, 0

    override_handler_deps(generation={"add_questions_fn": fake_add_questions})
    start_response = client.post(
        "/generate/start",
        data={"topic": "python", "count": "2", "language": "en"},
    )

    assert start_response.status_code == 202
    payload = start_response.get_json()
    assert payload["ok"] is True
    job_id = payload["job_id"]

    final_status = None
    for _ in range(40):
        status_response = client.get(f"/generate/progress/{job_id}")
        status_payload = status_response.get_json()
        assert status_response.status_code == 200
        assert status_payload["ok"] is True
        final_status = status_payload
        if status_payload["status"] == "completed":
            break
        time.sleep(0.01)

    assert final_status is not None
    assert final_status["status"] == "completed"
    assert final_status["inserted"] == 2
    assert final_status["requested_count"] == 2
    assert final_status["remaining"] == 0


def test_generate_start_rejects_invalid_payload(client):
    response = client.post(
        "/generate/start",
        data={"topic": "python", "count": "abc", "language": "en"},
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "Count must be an integer."
