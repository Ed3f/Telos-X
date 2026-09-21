from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from telos_x.ai.bert_common import load_label_names, load_thresholds


logger = logging.getLogger("TelegramExplorer")


class TargetNationBertPredictor:
    def __init__(self) -> None:
        base_dir = Path(__file__).resolve().parent

        self.artifacts_dir = base_dir / "bert_model"
        self.model_dir = self.artifacts_dir / "model"

        self.labels_path = (
            self.artifacts_dir / "label_names.json"
        )

        self.thresholds_path = (
            self.artifacts_dir / "thresholds.json"
        )

        self.enabled = False

        self.tokenizer = None
        self.model = None

        self.labels = []
        self.thresholds = {}

        self.device = torch.device(
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        required_paths = [
            self.model_dir,
            self.labels_path,
            self.thresholds_path,
        ]

        if not all(
            path.exists()
            for path in required_paths
        ):
            logger.warning(
                "[AI] Target Nation BERT artifacts not found."
            )
            return

        try:
            self.tokenizer = (
                AutoTokenizer.from_pretrained(
                    self.model_dir
                )
            )

            self.model = (
                AutoModelForSequenceClassification
                .from_pretrained(
                    self.model_dir
                )
            )

            self.labels = load_label_names(
                self.labels_path
            )

            self.thresholds = load_thresholds(
                self.thresholds_path
            )

            if not self.labels:
                raise ValueError(
                    "label_names.json is empty"
                )

            model_num_labels = int(
                getattr(
                    self.model.config,
                    "num_labels",
                    0,
                )
                or 0
            )

            if (
                model_num_labels
                and model_num_labels
                != len(self.labels)
            ):
                raise ValueError(
                    "Model/label mismatch: "
                    f"model={model_num_labels}, "
                    f"labels={len(self.labels)}"
                )

            self.model.to(
                self.device
            )

            self.model.eval()

            self.enabled = True

            logger.info(
                "[AI] Target Nation BERT loaded on %s",
                self.device,
            )

        except Exception:
            logger.exception(
                "[AI] Unable to initialize "
                "TargetNationBertPredictor."
            )

            self.enabled = False
            self.tokenizer = None
            self.model = None
            self.labels = []
            self.thresholds = {}

    def predict(
        self,
        text: str,
    ) -> Optional[Dict]:

        if (
            not self.enabled
            or self.model is None
            or self.tokenizer is None
        ):
            return None

        text = (
            text or ""
        ).strip()

        if not text:
            return {
                "labels": [],
                "scores": {},
                "top_label": None,
                "top_score": 0.0,
                "source_model": "bert",
            }

        try:
            inputs = self.tokenizer(
                text,
                truncation=True,
                padding=True,
                max_length=384,
                return_tensors="pt",
            )

            inputs = {
                key: value.to(
                    self.device
                )
                for key, value
                in inputs.items()
            }

            with torch.no_grad():
                logits = (
                    self.model(
                        **inputs
                    ).logits
                )

                probs = (
                    torch.sigmoid(
                        logits
                    )[0]
                    .detach()
                    .cpu()
                    .tolist()
                )

            score_map = {
                label: float(score)
                for label, score
                in zip(
                    self.labels,
                    probs,
                )
            }

            pred_labels = [
                label
                for label
                in self.labels
                if score_map[label]
                >= float(
                    self.thresholds.get(
                        label,
                        0.5,
                    )
                )
            ]

            top_label = (
                max(
                    score_map,
                    key=score_map.get,
                )
                if score_map
                else None
            )

            top_score = (
                score_map[top_label]
                if top_label
                else 0.0
            )

            return {
                "labels": pred_labels,
                "scores": score_map,
                "top_label": top_label,
                "top_score": top_score,
                "source_model": "bert",
            }

        except Exception:
            logger.exception(
                "[AI] Target Nation BERT "
                "inference failed."
            )

            return None