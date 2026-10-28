"""Machine Learning model wrapper (PyTorch / ONNX / Scikit-learn)."""
from typing import Any, List


class MLModel:
    def __init__(self):
        self.model: Any = None
        self.is_loaded: bool = False

    def load(self):
        """Mock loading weights (e.g. torch.load or onnxruntime.InferenceSession)."""
        self.model = "loaded_weights_instance"
        self.is_loaded = True

    def unload(self):
        """Clean up GPU memory / cache."""
        self.model = None
        self.is_loaded = False

    def predict(self, features: List[float]) -> dict:
        if not self.is_loaded:
            raise RuntimeError("Model is not loaded.")
        score = sum(features) / (len(features) or 1)
        label = "positive" if score >= 0.5 else "negative"
        confidence = min(max(abs(score), 0.52), 0.99)
        return {
            "label": label,
            "confidence": round(confidence, 4),
            "score": round(score, 4),
        }


ml_model = MLModel()
