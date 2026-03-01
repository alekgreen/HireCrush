import requests

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

