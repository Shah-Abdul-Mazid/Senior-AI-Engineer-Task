import time
from app.schemas.predict import PredictionRequest, PredictionResponse
from app.ml.model import ml_model
from app.ml.pipeline import pipeline


class InferenceService:
    def run_prediction(self, request: PredictionRequest) -> PredictionResponse:
        start_time = time.perf_counter()

        features = pipeline.preprocess(request.text)
        raw_output = ml_model.predict(features)
        output = pipeline.postprocess(raw_output)

        latency_ms = (time.perf_counter() - start_time) * 1000.0

        return PredictionResponse(
            label=output["label"],
            confidence=output["confidence"],
            score=output["score"],
            latency_ms=round(latency_ms, 2),
        )


inference_service = InferenceService()
