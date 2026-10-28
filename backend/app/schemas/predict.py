from pydantic import BaseModel


class PredictionRequest(BaseModel):
    text: str


class PredictionResponse(BaseModel):
    label: str
    confidence: float
    score: float
    latency_ms: float


class HealthResponse(BaseModel):
    status: str
    ai_status: str
    ml_model_loaded: bool
    device: str
