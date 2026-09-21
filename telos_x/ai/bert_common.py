from __future__ import annotations

import ast
import json
import random
from pathlib import Path
from typing import Callable, List, Sequence

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    hamming_loss,
)

from sklearn.model_selection import (
    train_test_split,
)

from sklearn.preprocessing import (
    MultiLabelBinarizer,
)

from torch.utils.data import Dataset

from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)


def seed_everything(
    seed: int = 42,
) -> None:

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(
            seed
        )


def parse_label_list(
    value,
):
    if isinstance(
        value,
        list,
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        try:
            parsed = (
                ast.literal_eval(
                    value
                )
            )

            if isinstance(
                parsed,
                list,
            ):
                return parsed

        except (
            ValueError,
            SyntaxError,
        ):
            return []

    return []


def clean_and_normalize_labels(
    labels: List[str],
) -> List[str]:

    labels = [
        label
        for label
        in labels
        if label
        not in (
            None,
            "",
            "undefined",
        )
    ]

    labels = [
        str(label)
        .strip()
        .lower()
        for label
        in labels
    ]

    return list(
        dict.fromkeys(
            labels
        )
    )


def compute_pos_weight(
    y: np.ndarray,
) -> torch.Tensor:

    positives = y.sum(
        axis=0
    )

    negatives = (
        y.shape[0]
        - positives
    )

    pos_weight = (
        negatives
        / np.clip(
            positives,
            1,
            None,
        )
    )

    return torch.tensor(
        pos_weight,
        dtype=torch.float,
    )


class TextMultiLabelDataset(
    Dataset
):
    def __init__(
        self,
        texts: Sequence[str],
        labels: np.ndarray,
        tokenizer,
        max_length: int = 384,
    ) -> None:

        self.texts = list(
            texts
        )

        self.labels = labels

        self.tokenizer = (
            tokenizer
        )

        self.max_length = (
            max_length
        )

    def __len__(
        self,
    ) -> int:

        return len(
            self.texts
        )

    def __getitem__(
        self,
        idx: int,
    ):
        text = str(
            self.texts[idx]
            or ""
        )

        encoded = (
            self.tokenizer(
                text,
                truncation=True,
                padding=False,
                max_length=(
                    self.max_length
                ),
                return_tensors="pt",
            )
        )

        item = {
            key: value.squeeze(0)
            for key, value
            in encoded.items()
        }

        item["labels"] = (
            torch.tensor(
                self.labels[idx],
                dtype=torch.float,
            )
        )

        return item


class WeightedBERTForMultiLabel(
    nn.Module
):
    def __init__(
        self,
        model_name: str,
        num_labels: int,
        pos_weight:
            torch.Tensor
            | None = None,
    ) -> None:

        super().__init__()

        self.model = (
            AutoModelForSequenceClassification
            .from_pretrained(
                model_name,
                num_labels=num_labels,
                problem_type=(
                    "multi_label_classification"
                ),
            )
        )

        # Necessario per compatibilità
        # con Trainer / Hugging Face.
        self.config = (
            self.model.config
        )

        self.pos_weight = (
            pos_weight
        )

    def forward(
        self,
        input_ids=None,
        attention_mask=None,
        labels=None,
        **kwargs,
    ):
        outputs = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            labels=None,
            **kwargs,
        )

        logits = (
            outputs.logits
        )

        loss = None

        if labels is not None:

            if (
                self.pos_weight
                is not None
            ):
                loss_fct = (
                    nn.BCEWithLogitsLoss(
                        pos_weight=(
                            self.pos_weight
                            .to(
                                logits.device
                            )
                        )
                    )
                )

            else:
                loss_fct = (
                    nn.BCEWithLogitsLoss()
                )

            loss = loss_fct(
                logits,
                labels,
            )

        return {
            "loss": loss,
            "logits": logits,
        }

    def save_pretrained(
        self,
        save_directory,
        **kwargs,
    ):
        return (
            self.model
            .save_pretrained(
                save_directory,
                **kwargs,
            )
        )


def sigmoid(
    x: np.ndarray,
) -> np.ndarray:

    return (
        1
        / (
            1
            + np.exp(-x)
        )
    )


def select_per_label_thresholds(
    y_true: np.ndarray,
    scores: np.ndarray,
    thr_grid: np.ndarray,
) -> np.ndarray:

    best_thr = np.full(
        y_true.shape[1],
        0.5,
        dtype=float,
    )

    for index in range(
        y_true.shape[1]
    ):
        best_f1 = -1.0
        best_t = 0.5

        y_label = (
            y_true[:, index]
        )

        score_label = (
            scores[:, index]
        )

        for threshold in thr_grid:

            pred = (
                score_label
                >= threshold
            ).astype(int)

            current_f1 = f1_score(
                y_label,
                pred,
                zero_division=0,
            )

            if (
                current_f1
                > best_f1
            ):
                best_f1 = (
                    current_f1
                )

                best_t = float(
                    threshold
                )

        best_thr[index] = (
            best_t
        )

    return best_thr


def save_bert_artifacts(
    *,
    model,
    tokenizer,
    output_dir:
        str | Path,
    label_names:
        List[str],
    thresholds:
        dict,
    final_test_results:
        dict | None = None,
) -> None:

    output_dir = Path(
        output_dir
    )

    model_dir = (
        output_dir
        / "model"
    )

    model_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    model.save_pretrained(
        model_dir
    )

    tokenizer.save_pretrained(
        model_dir
    )

    with open(
        output_dir
        / "label_names.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            label_names,
            file,
            ensure_ascii=False,
            indent=2,
        )

    with open(
        output_dir
        / "thresholds.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            thresholds,
            file,
            ensure_ascii=False,
            indent=2,
        )

    if (
        final_test_results
        is not None
    ):
        with open(
            output_dir
            / "final_test_results.json",
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                final_test_results,
                file,
                ensure_ascii=False,
                indent=2,
            )


def load_thresholds(
    path: str | Path,
) -> dict:

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


def load_label_names(
    path: str | Path,
) -> List[str]:

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


def train_bert_multilabel_task(
    *,
    dataset_path:
        str | Path,
    output_dir:
        str | Path,
    label_column: str,
    text_column:
        str = "message",
    cleaned_text_column:
        str = "text_clean",
    cleaning_fn:
        Callable[[str], str]
        | None = None,
    label_prepare_fn:
        Callable[
            [List[str]],
            List[str],
        ]
        | None = None,
    dataframe_prepare_fn:
        Callable[
            [pd.DataFrame],
            pd.DataFrame,
        ]
        | None = None,
    model_name:
        str = "bert-base-uncased",
    max_length:
        int = 384,
    num_epochs:
        int = 6,
    learning_rate:
        float = 2e-5,
    train_batch_size:
        int = 8,
    eval_batch_size:
        int = 16,
    seed:
        int = 42,
    validation_size:
        float = 0.15,
    test_size:
        float = 0.15,
) -> dict:

    seed_everything(
        seed
    )

    if (
        validation_size <= 0
        or test_size <= 0
    ):
        raise ValueError(
            "validation_size and "
            "test_size must be > 0"
        )

    if (
        validation_size
        + test_size
        >= 1
    ):
        raise ValueError(
            "validation_size + "
            "test_size must be < 1"
        )

    dataset_path = Path(
        dataset_path
    )

    output_dir = Path(
        output_dir
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not dataset_path.exists():
        raise FileNotFoundError(
            f"Dataset not found: "
            f"{dataset_path}"
        )

    if (
        dataset_path
        .suffix
        .lower()
        in {
            ".xlsx",
            ".xls",
        }
    ):
        df = pd.read_excel(
            dataset_path
        )

    else:
        df = pd.read_csv(
            dataset_path
        )

    # Target Nation può trasformare
    # il dataframe prima delle label.
    if (
        dataframe_prepare_fn
        is not None
    ):
        df = (
            dataframe_prepare_fn(
                df
            )
        )

    if (
        label_column
        not in df.columns
    ):
        raise KeyError(
            f"Missing label column: "
            f"{label_column}"
        )

    df[label_column] = (
        df[label_column]
        .apply(
            parse_label_list
        )
    )

    df[label_column] = (
        df[label_column]
        .apply(
            clean_and_normalize_labels
        )
    )

    # Activity / Attack Type
    # applicano qui il merge classi.
    if (
        label_prepare_fn
        is not None
    ):
        df[label_column] = (
            df[label_column]
            .apply(
                label_prepare_fn
            )
        )

    df = df[
        df[label_column]
        .map(len)
        > 0
    ].copy()

    if (
        cleaned_text_column
        not in df.columns
    ):
        if (
            text_column
            not in df.columns
        ):
            raise KeyError(
                "Missing text columns: "
                f"{cleaned_text_column}, "
                f"{text_column}"
            )

        source_text = (
            df[text_column]
            .fillna("")
            .astype(str)
        )

        if cleaning_fn is None:
            df[
                cleaned_text_column
            ] = source_text

        else:
            df[
                cleaned_text_column
            ] = source_text.apply(
                cleaning_fn
            )

    df[
        cleaned_text_column
    ] = (
        df[
            cleaned_text_column
        ]
        .fillna("")
        .astype(str)
    )

    df = df[
        df[
            cleaned_text_column
        ]
        .str.strip()
        .ne("")
    ].copy()

    if df.empty:
        raise ValueError(
            "No usable rows remain "
            "after preprocessing"
        )

    mlb = (
        MultiLabelBinarizer()
    )

    y = mlb.fit_transform(
        df[label_column]
    )

    label_names = list(
        mlb.classes_
    )

    if not label_names:
        raise ValueError(
            "No labels available "
            "after preprocessing"
        )

    texts = (
        df[
            cleaned_text_column
        ].to_numpy()
    )

    # =====================================================
    # TRAIN / VALIDATION / TEST
    # =====================================================

    x_train_val, x_test, \
    y_train_val, y_test = (
        train_test_split(
            texts,
            y,
            test_size=test_size,
            random_state=seed,
        )
    )

    validation_fraction = (
        validation_size
        / (
            1.0
            - test_size
        )
    )

    x_train, x_val, \
    y_train, y_val = (
        train_test_split(
            x_train_val,
            y_train_val,
            test_size=(
                validation_fraction
            ),
            random_state=seed,
        )
    )

    tokenizer = (
        AutoTokenizer
        .from_pretrained(
            model_name
        )
    )

    data_collator = (
        DataCollatorWithPadding(
            tokenizer=tokenizer
        )
    )

    train_ds = (
        TextMultiLabelDataset(
            texts=x_train,
            labels=y_train,
            tokenizer=tokenizer,
            max_length=max_length,
        )
    )

    validation_ds = (
        TextMultiLabelDataset(
            texts=x_val,
            labels=y_val,
            tokenizer=tokenizer,
            max_length=max_length,
        )
    )

    test_ds = (
        TextMultiLabelDataset(
            texts=x_test,
            labels=y_test,
            tokenizer=tokenizer,
            max_length=max_length,
        )
    )

    pos_weight = (
        compute_pos_weight(
            y_train
        )
    )

    model = (
        WeightedBERTForMultiLabel(
            model_name=model_name,
            num_labels=(
                y_train.shape[1]
            ),
            pos_weight=(
                pos_weight
            ),
        )
    )

    args = TrainingArguments(
        output_dir=str(
            output_dir
            / "tmp_train"
        ),

        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="epoch",

        learning_rate=(
            learning_rate
        ),

        per_device_train_batch_size=(
            train_batch_size
        ),

        per_device_eval_batch_size=(
            eval_batch_size
        ),

        num_train_epochs=(
            num_epochs
        ),

        weight_decay=0.01,
        warmup_ratio=0.1,

        save_total_limit=2,

        report_to="none",

        fp16=(
            torch.cuda
            .is_available()
        ),

        load_best_model_at_end=True,

        metric_for_best_model=(
            "eval_loss"
        ),

        greater_is_better=False,
    )

    trainer = Trainer(
        model=model,
        args=args,

        train_dataset=train_ds,
        eval_dataset=validation_ds,

        processing_class=(
            tokenizer
        ),

        data_collator=(
            data_collator
        ),

        callbacks=[
            EarlyStoppingCallback(
                early_stopping_patience=2
            )
        ],
    )

    trainer.train()

    # =====================================================
    # THRESHOLD SELECTION:
    # SOLO VALIDATION
    # =====================================================

    validation_output = (
        trainer.predict(
            validation_ds
        )
    )

    validation_probs = sigmoid(
        validation_output.predictions
    )

    threshold_grid = np.arange(
        0.10,
        0.91,
        0.05,
    )

    thresholds_array = (
        select_per_label_thresholds(
            y_val,
            validation_probs,
            threshold_grid,
        )
    )

    # =====================================================
    # TEST FINALE:
    # threshold già fissate
    # =====================================================

    test_output = (
        trainer.predict(
            test_ds
        )
    )

    test_probs = sigmoid(
        test_output.predictions
    )

    y_pred = (
        test_probs
        >= thresholds_array
        .reshape(
            1,
            -1,
        )
    ).astype(int)

    final_test_results = {
        "macro_f1": float(
            f1_score(
                y_test,
                y_pred,
                average="macro",
                zero_division=0,
            )
        ),

        "micro_f1": float(
            f1_score(
                y_test,
                y_pred,
                average="micro",
                zero_division=0,
            )
        ),

        "hamming": float(
            hamming_loss(
                y_test,
                y_pred,
            )
        ),

        "subset_acc": float(
            accuracy_score(
                y_test,
                y_pred,
            )
        ),

        "train_samples": int(
            len(x_train)
        ),

        "validation_samples": int(
            len(x_val)
        ),

        "test_samples": int(
            len(x_test)
        ),
    }

    thresholds = {
        label: float(
            threshold
        )

        for label, threshold
        in zip(
            label_names,
            thresholds_array,
        )
    }

    save_bert_artifacts(
        model=trainer.model,
        tokenizer=tokenizer,
        output_dir=output_dir,
        label_names=label_names,
        thresholds=thresholds,
        final_test_results=(
            final_test_results
        ),
    )

    return {
        "label_names": (
            label_names
        ),

        "thresholds": (
            thresholds
        ),

        "final_test_results": (
            final_test_results
        ),

        "output_dir": str(
            output_dir
        ),
    }