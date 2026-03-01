from tests.support import insert_question


def test_topics_route_lists_topic_cards(client):
    insert_question("Explain Python decorators.", topic="python", topic_color="emerald")
    insert_question("What is a SQL index?", topic="sql", topic_color="rose")

    res = client.get("/topics")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Topics" in body
    assert "python" in body
    assert "sql" in body
    assert "Open topic" in body


def test_topics_route_detail_filters_by_topic(client):
    insert_question("Explain Python decorators.", topic="python")
    insert_question("What is a SQL index?", topic="sql")

    res = client.get("/topics?topic=python")
    body = res.data.decode("utf-8")

    assert res.status_code == 200
    assert "Viewing questions for this topic." in body
    assert "Explain Python decorators." in body
    assert "What is a SQL index?" not in body

