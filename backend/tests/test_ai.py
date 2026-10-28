def test_health_endpoint(client):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["ml_model_loaded"] is True


def test_predict_endpoint(client):
    payload = {"text": "FastAPI with PyTorch is super fast and amazing!"}
    res = client.post("/api/v1/predict/", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "label" in data
    assert "confidence" in data
    assert "latency_ms" in data
    assert data["confidence"] > 0


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
