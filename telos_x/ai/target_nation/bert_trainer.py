from __future__ import annotations

from pathlib import Path

from telos_x.ai.target_nation.preprocessing import (
    prepare_nation_dataframe,
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
    / "telegram_dataset_nation_classification.xlsx"
)

DEFAULT_OUTPUT_DIR = (
    Path(__file__)
    .resolve()
    .parent
    / "bert_model"
)

DEFAULT_LABEL_COLUMN = (
    "continent"
)

DEFAULT_TEXT_COLUMN = (
    "message"
)


def train_target_nation_bert(
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

        dataframe_prepare_fn=(
            prepare_nation_dataframe
        ),
    )


if __name__ == "__main__":
    result = (
        train_target_nation_bert()
    )

    print(result)