# 🚀 My Full-Stack FastAPI AI & ML Service

> Scaffolded by [fastapi-struct](https://pypi.org/project/fastapi-struct/) — `fastapi-struct my_project -t all`

A **production-ready** FastAPI project combining enterprise REST API patterns with full AI & ML capabilities — all wired up and ready to demo in under 60 seconds.

---

## ⚡ Quick Start

```bash
# 1. Create virtual environment
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env   # then edit .env with your API keys

# 4. Run the server
uvicorn app.main:app --reload
```

Open → **http://localhost:8000/docs** — interactive Swagger UI, fully wired.

---

## 🎯 What's Available Right Now (No Setup Needed)

All endpoints work immediately with mock/demo responses — no real API keys required to test:

### 🤖 AI & GenAI

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/chat/` | GenAI chat completion |
| `POST` | `/api/v1/chat/stream` | Token-by-token streaming (SSE) |
| `POST` | `/api/v1/rag/query` | RAG vector search + LLM answer |
| `POST` | `/api/v1/predict/` | ML model inference |
| `GET`  | `/api/v1/health` | GPU / device readiness probe |

### 🏗️ Traditional Web API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET`  | `/api/v1/users/` | List all users |
| `POST` | `/api/v1/users/` | Create a user |
| `GET`  | `/api/v1/users/{id}` | Get user by ID |
| `GET`  | `/api/v1/items/` | List all items |
| `POST` | `/api/v1/items/` | Create an item |
| `GET`  | `/api/v1/items/{id}` | Get item by ID |

---

## 🧪 Try It Right Now — Demo Requests

### 1. Health Check
```bash
curl http://localhost:8000/api/v1/health
```
```json
{
  "status": "healthy",
  "ai_status": "ready",
  "ml_model_loaded": true,
  "device": "cpu"
}
```

---

### 2. GenAI Chat Completion
```bash
curl -X POST http://localhost:8000/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What is FastAPI?"}]}'
```
```json
{
  "message": {
    "role": "assistant",
    "content": "[AI (gpt-4o-mini)]: Response to 'What is FastAPI?'..."
  },
  "model": "gpt-4o-mini",
  "tokens_used": 12,
  "latency_ms": 0.45
}
```

---

### 3. Token Streaming (Server-Sent Events)
```bash
curl -X POST http://localhost:8000/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Tell me about RAG"}]}'
```
```
data: Echoing
data: 'Tell
data: me
data: about
data: RAG'.
data: [DONE]
```

---

### 4. RAG Vector Search
```bash
curl -X POST http://localhost:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How does FastAPI help AI engineers?", "top_k": 2}'
```
```json
{
  "query": "How does FastAPI help AI engineers?",
  "answer": "Based on retrieved context [...], answer generated.",
  "sources": [
    {"id": "doc_1", "text": "FastAPI provides high-performance...", "score": 0.96},
    {"id": "doc_2", "text": "AI Engineers use StreamingResponse...", "score": 0.92}
  ],
  "latency_ms": 0.12
}
```

---

### 5. ML Model Inference
```bash
curl -X POST http://localhost:8000/api/v1/predict/ \
  -H "Content-Type: application/json" \
  -d '{"text": "This product is absolutely amazing and fast!"}'
```
```json
{
  "label": "positive",
  "confidence": 0.72,
  "score": 0.72,
  "latency_ms": 0.08
}
```

---

### 6. Create a User
```bash
curl -X POST http://localhost:8000/api/v1/users/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Jane Doe", "email": "jane@example.com", "password": "secret123"}'
```
```json
{"id": 1, "name": "Jane Doe", "email": "jane@example.com"}
```

---

### 7. Create an Item
```bash
curl -X POST http://localhost:8000/api/v1/items/ \
  -H "Content-Type: application/json" \
  -d '{"title": "GPU Server", "description": "NVIDIA A100", "price": 12999.99}'
```
```json
{"id": 1, "title": "GPU Server", "description": "NVIDIA A100", "price": 12999.99}
```

---

## 🧪 Run Tests

```bash
pytest
```

Expected output:
```
tests/test_ai.py::test_health_endpoint     PASSED
tests/test_ai.py::test_predict_endpoint    PASSED
tests/test_ai.py::test_chat_endpoint       PASSED
tests/test_ai.py::test_rag_endpoint        PASSED
tests/test_web.py::test_create_and_read_item   PASSED
tests/test_web.py::test_get_nonexistent_item   PASSED
tests/test_web.py::test_create_and_read_user   PASSED
tests/test_web.py::test_duplicate_user_email   PASSED

8 passed in 0.XXs
```

---

## 🗂️ Project Structure

```
app/
├── main.py                    # FastAPI app + lifespan model loader
├── api/v1/routes/
│   ├── health.py              # GPU & readiness probe
│   ├── chat.py                # LLM chat + SSE streaming
│   ├── rag.py                 # Vector retrieval + LLM
│   ├── predict.py             # ML inference
│   ├── users.py               # User CRUD
│   └── items.py               # Item CRUD
├── ai/
│   ├── llm.py                 # Async token streaming client
│   ├── prompt.py              # System prompt templates
│   └── rag.py                 # VectorRetriever (swap for Pinecone/Qdrant/ChromaDB)
├── ml/
│   ├── model.py               # MLModel wrapper (swap for PyTorch/ONNX/HuggingFace)
│   └── pipeline.py            # Pre/post-processing pipeline
├── schemas/                   # Pydantic models for all endpoints
├── services/                  # Business logic layer
├── repositories/              # DB query layer (SQLAlchemy/SQLModel ready)
├── models/                    # ORM models (dataclasses → swap for SQLModel Tables)
└── core/
    ├── config.py              # All settings via .env
    ├── database.py            # DB engine stub (plug in your DB)
    └── security.py            # Password hashing
```

---

## 🔌 Plug In Real Services

| What to swap | Where |
|---|---|
| OpenAI / Anthropic / Gemini | `app/ai/llm.py` → replace mock with real SDK call |
| Pinecone / Qdrant / ChromaDB | `app/ai/rag.py` → replace `_store` with vector DB client |
| PyTorch / ONNX / HuggingFace | `app/ml/model.py` → replace mock with `torch.load()` / `onnxruntime` |
| PostgreSQL / SQLite / MySQL | `app/core/database.py` → add SQLAlchemy engine + sessions |

---

## 🔑 Environment Variables (`.env`)

| Variable | Default | Description |
|---|---|---|
| `PROJECT_NAME` | `FastAPI Full-Stack AI & ML Service` | App display name |
| `OPENAI_API_KEY` | `sk-placeholder` | Your OpenAI / LLM API key |
| `LLM_MODEL` | `gpt-4o-mini` | LLM model name |
| `DEVICE` | `cpu` | `cpu` or `cuda` |
| `SECRET_KEY` | *(change this!)* | JWT / session secret |
| `DEBUG` | `true` | Debug mode |

---

## 📦 Generated by `fastapi-struct`

```bash
pip install fastapi-struct
fastapi-struct my_project -t all    # this template
fastapi-struct my_project           # AI/ML only (default)
fastapi-struct my_project -t basic  # web API only
fastapi-struct --list-templates     # see all options
```

[PyPI](https://pypi.org/project/fastapi-struct/) · [FastAPI Docs](https://fastapi.tiangolo.com)
