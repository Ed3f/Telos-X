from __future__ import annotations

from pathlib import Path

from telos_x.ai.activity.preprocessing import clean_text_activity
from telos_x.ai.bert_common import train_bert_multilabel_task


DEFAULT_DATASET_PATH = "dataset/telegram_dataset_activity_classification.xlsx"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "bert_model"
DEFAULT_LABEL_COLUMN = "activity_labels"
DEFAULT_TEXT_COLUMN = "message"


def train_activity_bert(
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
):
    return train_bert_multilabel_task(
        dataset_path=dataset_path,
        output_dir=output_dir,
        label_column=DEFAULT_LABEL_COLUMN,
        text_column=DEFAULT_TEXT_COLUMN,
        cleaned_text_column="text_clean",
        cleaning_fn=clean_text_activity,
    )


if __name__ == "__main__":
    result = train_activity_bert()
    print(result)