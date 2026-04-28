from __future__ import annotations

import ast
import json
import random
from pathlib import Path
from typing import Callable, Dict, List, Sequence

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import accuracy_score, f1_score, hamming_loss
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MultiLabelBinarizer
from torch.utils.data import Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)


def seed_everything(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def parse_label_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        try:
            parsed = ast.literal_eval(x)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
    return []


def clean_and_normalize_labels(labels: List[str]) -> List[str]:
    labels = [l for l in labels if l not in (None, "", "undefined")]
    labels = [str(l).strip().lower() for l in labels]
    return list(dict.fromkeys(labels))


def compute_pos_weight(y: np.ndarray) -> torch.Tensor:
    positives = y.sum(axis=0)
    negatives = y.shape[0] - positives
    pos_weight = negatives / np.clip(positives, 1, None)
    return torch.tensor(pos_weight, dtype=torch.float)


class TextMultiLabelDataset(Dataset):
    def __init__(
        self,
        texts: Sequence[str],
        labels: np.ndarray,
        tokenizer,
        max_length: int = 384,
    ) -> None:
        self.texts = list(texts)
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, idx: int):
        text = str(self.texts[idx] or "")
        encoded = self.tokenizer(
            text,
            truncation=True,
            padding=False,
            max_length=self.max_length,
            return_tensors="pt",
        )
        item = {k: v.squeeze(0) for k, v in encoded.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.float)
        return item


class WeightedBERTForMultiLabel(nn.Module):
    def __init__(
        self,
        model_name: str,
        num_labels: int,
        pos_weight: torch.Tensor | None = None,
    ):
        super().__init__()
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=num_labels,
            problem_type="multi_label_classification",
        )
        self.pos_weight = pos_weight

    def forward(self, input_ids=None, attention_mask=None, labels=None, **kwargs):
        outputs = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=None,
        )
        logits = outputs.logits

        loss = None
        if labels is not None:
            if self.pos_weight is not None:
                loss_fct = nn.BCEWithLogitsLoss(
                    pos_weight=self.pos_weight.to(logits.device)
                )
            else:
                loss_fct = nn.BCEWithLogitsLoss()

            loss = loss_fct(logits, labels)

        return {"loss": loss, "logits": logits}


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def select_per_label_thresholds(
    y_true: np.ndarray,
    scores: np.ndarray,
    thr_grid: np.ndarray,
) -> np.ndarray:
    best_thr = np.full(y_true.shape[1], 0.5, dtype=float)

    for j in range(y_true.shape[1]):
        best_f1 = -1.0
        best_t = 0.5
        yj = y_true[:, j]
        sj = scores[:, j]

        for t in thr_grid:
            pred = (sj >= t).astype(int)
            f1 = f1_score(yj, pred, zero_division=0)
            if f1 > best_f1:
                best_f1 = f1
                best_t = float(t)

        best_thr[j] = best_t

    return best_thr


def save_bert_artifacts(
    *,
    model,
    tokenizer,
    output_dir: str | Path,
    label_names: List[str],
    thresholds: dict,
    final_test_results: dict | None = None,
) -> None:
    output_dir = Path(output_dir)
    model_dir = output_dir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)

    model.save_pretrained(model_dir)
    tokenizer.save_pretrained(model_dir)

    with open(output_dir / "label_names.json", "w", encoding="utf-8") as f:
        json.dump(label_names, f, ensure_ascii=False, indent=2)

    with open(output_dir / "thresholds.json", "w", encoding="utf-8") as f:
        json.dump(thresholds, f, ensure_ascii=False, indent=2)

    if final_test_results is not None:
        with open(output_dir / "final_test_results.json", "w", encoding="utf-8") as f:
            json.dump(final_test_results, f, ensure_ascii=False, indent=2)


def load_thresholds(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_label_names(path: str | Path) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def train_bert_multilabel_task(
    *,
    dataset_path: str | Path,
    output_dir: str | Path,
    label_column: str,
    text_column: str = "message",
    cleaned_text_column: str = "text_clean",
    cleaning_fn: Callable[[str], str] | None = None,
    model_name: str = "bert-base-uncased",
    max_length: int = 384,
    num_epochs: int = 6,
    learning_rate: float = 2e-5,
    train_batch_size: int = 8,
    eval_batch_size: int = 16,
    seed: int = 42,
    test_size: float = 0.2,
) -> dict:
    seed_everything(seed)

    dataset_path = Path(dataset_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if dataset_path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(dataset_path)
    else:
        df = pd.read_csv(dataset_path)

    df[label_column] = df[label_column].apply(parse_label_list)
    df[label_column] = df[label_column].apply(clean_and_normalize_labels)
    df = df[df[label_column].map(len) > 0].copy()

    if cleaned_text_column not in df.columns:
        if cleaning_fn is None:
            df[cleaned_text_column] = df[text_column].fillna("").astype(str)
        else:
            df[cleaned_text_column] = df[text_column].fillna("").astype(str).apply(cleaning_fn)

    mlb = MultiLabelBinarizer()
    y = mlb.fit_transform(df[label_column])
    label_names = list(mlb.classes_)

    x_train, x_test, y_train, y_test = train_test_split(
        df[[cleaned_text_column]],
        y,
        test_size=test_size,
        random_state=seed,
    )

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

    train_ds = TextMultiLabelDataset(
        texts=x_train[cleaned_text_column].tolist(),
        labels=y_train,
        tokenizer=tokenizer,
        max_length=max_length,
    )
    test_ds = TextMultiLabelDataset(
        texts=x_test[cleaned_text_column].tolist(),
        labels=y_test,
        tokenizer=tokenizer,
        max_length=max_length,
    )

    pos_weight = compute_pos_weight(y_train)
    model = WeightedBERTForMultiLabel(
        model_name=model_name,
        num_labels=y_train.shape[1],
        pos_weight=pos_weight,
    )

    args = TrainingArguments(
        output_dir=str(output_dir / "tmp_train"),
        eval_strategy="no",
        save_strategy="epoch",
        logging_strategy="epoch",
        learning_rate=learning_rate,
        per_device_train_batch_size=train_batch_size,
        per_device_eval_batch_size=eval_batch_size,
        num_train_epochs=num_epochs,
        weight_decay=0.01,
        warmup_ratio=0.1,
        save_total_limit=1,
        report_to="none",
        fp16=torch.cuda.is_available(),
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        tokenizer=tokenizer,
        data_collator=data_collator,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    trainer.train()

    pred_output = trainer.predict(test_ds)
    probs = sigmoid(pred_output.predictions)

    thr_grid = np.arange(0.10, 0.91, 0.05)
    thr = select_per_label_thresholds(y_test, probs, thr_grid)
    y_pred = (probs >= thr.reshape(1, -1)).astype(int)

    final_test_results = {
        "macro_f1": float(f1_score(y_test, y_pred, average="macro", zero_division=0)),
        "micro_f1": float(f1_score(y_test, y_pred, average="micro", zero_division=0)),
        "hamming": float(hamming_loss(y_test, y_pred)),
        "subset_acc": float(accuracy_score(y_test, y_pred)),
    }

    thresholds = {lab: float(t) for lab, t in zip(label_names, thr)}

    save_bert_artifacts(
        model=trainer.model,
        tokenizer=tokenizer,
        output_dir=output_dir,
        label_names=label_names,
        thresholds=thresholds,
        final_test_results=final_test_results,
    )

    return {
        "label_names": label_names,
        "thresholds": thresholds,
        "final_test_results": final_test_results,
        "output_dir": str(output_dir),
    }