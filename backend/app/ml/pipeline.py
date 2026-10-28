"""Feature engineering & preprocessing pipeline."""
from typing import List


class MLPipeline:
    def preprocess(self, text: str) -> List[float]:
        words = text.strip().split()
        return [min(len(w) / 10.0, 1.0) for w in words] or [0.0]

    def postprocess(self, raw_prediction: dict) -> dict:
        return raw_prediction


pipeline = MLPipeline()
