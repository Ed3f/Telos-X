from __future__ import annotations

from pathlib import Path

from telos_x.ai.attack_type.preprocessing import (
    clean_text_for_inference,
    merge_attack_classes,
)

from telos_x.ai.bert_common import (
    train_bert_multilabel_task,
)


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

DEFAULT_DATASET_PATH = (
    PROJECT_ROOT
    / "dataset"
    / "telegram_dataset_attack_type_classification 1.xlsx"
)

DEFAULT_OUTPUT_DIR = (
    Path(__file__)
    .resolve()
    .parent
    / "bert_model"
)

DEFAULT_LABEL_COLUMN = (
    "attack_type"
)

DEFAULT_TEXT_COLUMN = (
    "message"
)


def train_attack_type_bert(
    dataset_path:
        str | Path = DEFAULT_DATASET_PATH,
    output_dir:
        str | Path = DEFAULT_OUTPUT_DIR,
):
    return train_bert_multilabel_task(
        dataset_path=dataset_path,
        output_dir=output_dir,

        label_column=(
            DEFAULT_LABEL_COLUMN
        ),

        text_column=(
            DEFAULT_TEXT_COLUMN
        ),

        cleaned_text_column=(
            "text_clean"
        ),

        cleaning_fn=(
            clean_text_for_inference
        ),

        label_prepare_fn=(
            merge_attack_classes
        ),
    )


if __name__ == "__main__":
    result = (
        train_attack_type_bert()
    )

    print(result)