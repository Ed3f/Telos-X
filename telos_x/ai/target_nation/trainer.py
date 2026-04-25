import json
from pathlib import Path

import joblib
import pandas as pd

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import MultiLabelBinarizer, FunctionTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.linear_model import LogisticRegression

from .preprocessing import prepare_nation_dataframe, meta_features_df


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_PATH = BASE_DIR / "Dataset" / "telegram_dataset_nation_classification.xlsx"
MODELS_DIR = Path(__file__).resolve().parent / "models"


def build_pipeline():
    tfidf_word = TfidfVectorizer(
        lowercase=True,
        strip_accents="unicode",
        min_df=5,
        max_df=0.8,
        ngram_range=(1, 3),
        sublinear_tf=True,
        token_pattern=r"(?u)\b[\w\-]{2,}\b",
    )

    tfidf_char = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(3, 5),
        min_df=5,
        sublinear_tf=True,
    )

    features = ColumnTransformer(
        transformers=[
            ("tfidf_word", tfidf_word, "text_clean"),
            ("tfidf_char", tfidf_char, "text_clean"),
            ("meta", FunctionTransformer(meta_features_df, validate=False), ["text_clean"]),
        ],
        remainder="drop",
    )

    lr_base = LogisticRegression(
        max_iter=3000,
        solver="lbfgs",
        tol=1e-4,
        random_state=42,
    )

    return Pipeline([
        ("features", features),
        ("clf", OneVsRestClassifier(lr_base, n_jobs=1)),
    ])


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset non trovato: {DATA_PATH}")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(DATA_PATH)
    df = prepare_nation_dataframe(df)

    X = df[["text_clean"]].copy()

    mlb = MultiLabelBinarizer()
    Y = mlb.fit_transform(df["continent"])

    pipeline = build_pipeline()
    pipeline.fit(X, Y)

    joblib.dump(pipeline, MODELS_DIR / "pipeline.joblib")
    joblib.dump(list(mlb.classes_), MODELS_DIR / "labels.joblib")

    thresholds = {label: 0.5 for label in mlb.classes_}
    with open(MODELS_DIR / "thresholds.json", "w", encoding="utf-8") as f:
        json.dump(thresholds, f, indent=2)

    print("Target nation model salvato correttamente.")


if __name__ == "__main__":
    main()