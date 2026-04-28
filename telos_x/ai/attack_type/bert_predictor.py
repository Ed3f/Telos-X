from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from telos_x.ai.bert_common import load_label_names, load_thresholds


class AttackTypeBertPredictor:
    def __init__(self) -> None:
        base_dir = Path(__file__).resolve().parent
        self.artifacts_dir = base_dir / "bert_model"
        self.model_dir = self.artifacts_dir / "model"

        self.enabled = self.model_dir.exists()
        self.tokenizer = None
        self.model = None
        self.labels = []
        self.thresholds = {}

        if not self.enabled:
            return

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_dir)
        self.model.eval()

        self.labels = load_label_names(self.artifacts_dir / "label_names.json")
        self.thresholds = load_thresholds(self.artifacts_dir / "thresholds.json")

    def predict(self, text: str) -> Optional[Dict]:
        if not self.enabled or self.model is None or self.tokenizer is None:
            return None

        text = (text or "").strip()
        if not text:
            return {
                "labels": [],
                "scores": {},
                "top_label": None,
                "top_score": 0.0,
                "source_model": "bert",
            }

        inputs = self.tokenizer(
            text,
            truncation=True,
            padding=True,
            max_length=384,
            return_tensors="pt",
        )

        with torch.no_grad():
            logits = self.model(**inputs).logits
            probs = torch.sigmoid(logits)[0].cpu().tolist()

        score_map = {label: float(score) for label, score in zip(self.labels, probs)}
        pred_labels = [
            label for label in self.labels
            if score_map[label] >= self.thresholds.get(label, 0.5)
        ]
        top_label = max(score_map, key=score_map.get) if score_map else None
        top_score = score_map[top_label] if top_label else 0.0

        return {
            "labels": pred_labels,
            "scores": score_map,
            "top_label": top_label,
            "top_score": top_score,
            "source_model": "bert",
        }