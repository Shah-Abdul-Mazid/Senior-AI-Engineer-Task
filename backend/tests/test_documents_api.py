"""Automated tests for Document Intelligence REST API Endpoints (Task 4)."""
import io
import pytest
from fastapi.testclient import TestClient


def test_root_endpoint_capabilities(client: TestClient):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert "capabilities" in data
    assert any("Document Ingestion" in c for c in data["capabilities"])
    assert any("Cross-Document Verification" in c for c in data["capabilities"])


def test_health_check(client: TestClient):
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"


def test_upload_invalid_extension(client: TestClient):
    # Upload an unsupported file format (.exe)
    file_content = b"fake binary content"
    files = [("files", ("malicious.exe", io.BytesIO(file_content), "application/octet-stream"))]
    res = client.post("/api/v1/documents/upload", files=files)
    assert res.status_code == 202
    data = res.json()
    assert data["successful"] == 0
    assert len(data["failed"]) == 1
    assert "not supported" in data["failed"][0]["error"].lower()


def test_search_endpoint_contract(client: TestClient):
    payload = {
        "query": "ACME Supplies",
        "search_type": "keyword",
        "top_k": 5
    }
    res = client.post("/api/v1/documents/search", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "results" in data
    assert "latency_ms" in data
    assert data["query"] == "ACME Supplies"


def test_clear_documents_endpoint(client: TestClient):
    # Test clearing documents by status and all
    res = client.delete("/api/v1/documents/clear?status=requires_review")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "deleted_count" in data

    res_all = client.delete("/api/v1/documents/clear?status=all")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["status"] == "success"
    assert "deleted_count" in data_all
