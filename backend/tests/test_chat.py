def test_chat_endpoint(client):
    payload = {
        "messages": [{"role": "user", "content": "Hello AI Assistant"}]
    }
    res = client.post("/api/v1/chat/", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["message"]["role"] == "assistant"
    assert "content" in data["message"]


def test_rag_endpoint(client):
    payload = {"query": "Tell me about FastAPI"}
    res = client.post("/api/v1/rag/query", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert len(data["sources"]) > 0
