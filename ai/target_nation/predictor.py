import json
from pathlib import Path

import joblib
import pandas as pd

from .preprocessing import clean_text_nation


class TargetNationPredictor:
    def __init__(self):
        models_dir = Path(__file__).resolve().parent / "models"

        self.model = joblib.load(models_dir / "pipeline.joblib")
        self.labels = joblib.load(models_dir / "labels.joblib")

        with open(models_dir / "thresholds.json", "r", encoding="utf-8") as f:
            self.thresholds = json.load(f)

    def predict(self, text: str) -> dict:
        text = clean_text_nation(text)

        if not text:
            return {"labels": [], "scores": {}, "top_label": None, "top_score": 0.0}

        X = pd.DataFrame([{"text_clean": text}])

        if hasattr(self.model, "predict_proba"):
            raw_scores = self.model.predict_proba(X)
            if isinstance(raw_scores, list):
                import numpy as np
                raw_scores = np.column_stack([p[:, 1] for p in raw_scores])
            raw_scores = raw_scores[0]
        else:
            raw_scores = self.model.decision_function(X)[0]

        score_map = {label: float(score) for label, score in zip(self.labels, raw_scores)}
        pred_labels = [label for label in self.labels if score_map[label] >= self.thresholds.get(label, 0.5)]
        top_label = max(score_map, key=score_map.get) if score_map else None
        top_score = score_map[top_label] if top_label else 0.0

        return {
            "labels": pred_labels,
            "scores": score_map,
            "top_label": top_label,
            "top_score": top_score,
        }