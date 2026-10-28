from fastapi import APIRouter, HTTPException, status
from app.schemas.predict import PredictionRequest, PredictionResponse
from app.services.inference import inference_service

router = APIRouter(prefix="/predict", tags=["ML Inference"])


@router.post("/", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
async def predict(payload: PredictionRequest):
    """Run model inference."""
    try:
        return inference_service.run_prediction(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference error: {str(exc)}",
        )
