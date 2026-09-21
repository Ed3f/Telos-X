from __future__ import annotations

from pathlib import Path

from telos_x.ai.activity.preprocessing import (
    clean_text_for_inference,
    merge_activity_classes,
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
    / "telegram_dataset_activity_classification.xlsx"
)

DEFAULT_OUTPUT_DIR = (
    Path(__file__)
    .resolve()
    .parent
    / "bert_model"
)

DEFAULT_LABEL_COLUMN = (
    "activity_labels"
)

DEFAULT_TEXT_COLUMN = (
    "message"
)


def train_activity_bert(
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
            merge_activity_classes
        ),
    )


if __name__ == "__main__":
    result = (
        train_activity_bert()
    )

    print(result)