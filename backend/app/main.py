from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.v1.api import api_router
from app.ml.model import ml_model
from app.core.database import init_db
from app.core.mongodb import mongo_manager
from app.storage.file_store import ensure_upload_dir
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure upload directories and load models
    print("\n[STARTUP] Initializing AI Document Intelligence Engine...")
    ensure_upload_dir()
    ml_model.load()

    # Attempt to initialize database tables (PostgreSQL & MongoDB)
    try:
        await init_db()
        print("[OK] PostgreSQL database tables and pgvector extension initialized.")
    except Exception as e:
        logger.warning(f"Could not connect to PostgreSQL database on startup: {e}. Running in memory-safe mode.")

    try:
        mongo_connected = await mongo_manager.connect()
        if mongo_connected:
            print("[OK] MongoDB Atlas initialized with text & compound search indexes.")
        else:
            print("[INFO] MongoDB not connected, proceeding with local relational storage.")
    except Exception as e:
        logger.warning(f"Could not connect to MongoDB on startup: {e}")

    print(f"[OK] AI LLM & Extraction Engine Ready: '{settings.LLM_MODEL}'\n")
    yield
    # Shutdown: Clean up resources
    print("[SHUTDOWN] Shutting down AI/ML models...")
    ml_model.unload()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Production AI-Powered Document Intelligence System: "
        "Automated multi-format OCR (PDF, Images), Spreadsheet parsing (XLSX, CSV), "
        "LLM-based structured extraction, mathematical validation, cross-document verification, "
        "semantic search, and REST API."
    ),
    version="1.1.0",
    lifespan=lifespan,
)

# Configure CORS for frontend dev and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:4173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount all API routes under /api/v1
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["health"])
async def root():
    """Root health check — lists system capabilities."""
    return {
        "service": settings.PROJECT_NAME,
        "version": "1.1.0",
        "status": "operational",
        "capabilities": [
            "Document Ingestion & Multi-Format OCR (/api/v1/documents/upload)",
            "AI Invoice Extraction & Line Items (/api/v1/documents/{id}/result)",
            "Automated Validation & Manual Review (/api/v1/documents/{id}/corrections)",
            "Cross-Document Verification (PDF vs PDF / Excel) (/api/v1/documents/cross-verify)",
            "Semantic & Hybrid Vector Search (/api/v1/documents/search)",
            "GenAI Chat & Token Streaming (/api/v1/chat)",
            "Health & Readiness Probe (/api/v1/health)",
        ],
        "device": "cpu",
        "docs": "/docs",
    }
