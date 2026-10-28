from fastapi import APIRouter
from app.core.config import settings
from app.ml.model import ml_model
from app.schemas.predict import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    return {
        "status": "healthy",
        "ai_status": "ready",
        "ml_model_loaded": ml_model.is_loaded,
        "device": settings.DEVICE,
    }
