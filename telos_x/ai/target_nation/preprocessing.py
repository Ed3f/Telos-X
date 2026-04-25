import ast
import re
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS


STOPWORDS = ENGLISH_STOP_WORDS

EUROPE = {
    "uk", "united kingdom", "great britain", "britain", "england",
    "ukraine", "poland", "italy", "spain", "germany", "france",
    "belgium", "portugal", "sweden", "norway", "netherlands", "greece",
}
AMERICA = {
    "usa", "us", "united states", "canada", "mexico",
    "brazil", "argentina", "chile", "peru", "colombia", "venezuela",
}
ASIA = {
    "india", "turkey", "china", "japan", "south korea", "korea",
    "pakistan", "indonesia", "philippines", "bangladesh",
}
AFRICA = {
    "nigeria", "egypt", "south africa", "kenya", "morocco", "algeria",
    "ghana", "ethiopia",
}
OCEANIA = {"australia", "new zealand", "nz"}

REGIONS = [
    (EUROPE, "Europe"),
    (AMERICA, "America"),
    (ASIA, "Asia"),
    (AFRICA, "Africa"),
    (OCEANIA, "Oceania"),
]


def parse_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        try:
            return ast.literal_eval(x)
        except Exception:
            return []
    return []


def map_country(country: str) -> str:
    c = str(country).strip().lower()
    for group, name in REGIONS:
        if c in group:
            return name
    return "Unknown"


def to_continents(xs):
    if not isinstance(xs, list):
        return []
    mapped = [map_country(x) for x in xs]
    mapped = [m for m in mapped if m != "Unknown"]
    return list(dict.fromkeys(mapped))


def clean_text_nation(text: str, remove_stopwords: bool = True) -> str:
    if pd.isna(text):
        return ""
    text = str(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if remove_stopwords:
        tokens = [t for t in text.split() if t not in STOPWORDS]
        text = " ".join(tokens)
    return text


def prepare_nation_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "target_countries_list" not in df.columns and "target_countries" in df.columns:
        df["target_countries_list"] = df["target_countries"].apply(parse_list)

    if "target_countries_list" in df.columns:
        mask_undefined = df["target_countries_list"].apply(
            lambda xs: isinstance(xs, list) and any(str(x).lower() == "undefined" for x in xs)
        )
        df = df[~mask_undefined].copy()
        df["continent"] = df["target_countries_list"].apply(to_continents)
    elif "target_country" in df.columns:
        df = df[df["target_country"].str.lower().ne("undefined")].copy()
        df["continent"] = df["target_country"].apply(lambda x: [] if pd.isna(x) else [map_country(x)])
        df["continent"] = df["continent"].apply(lambda xs: [x for x in xs if x != "Unknown"])
    else:
        df["continent"] = [[] for _ in range(len(df))]

    df = df[df["continent"].map(len) > 0].copy()

    text_col = None
    for col in ["text", "message", "content", "text_clean"]:
        if col in df.columns:
            text_col = col
            break

    if text_col is not None:
        df["text_clean"] = df[text_col].apply(clean_text_nation)
    else:
        df["text_clean"] = ""

    return df


def meta_features_df(X):
    """
    Notebook nation:
    3 meta-features
    - lunghezza messaggio
    - count keyword paesi
    - count country-like domains
    """
    if hasattr(X, "iloc"):
        s_list = X.iloc[:, 0].astype(str).tolist()
    else:
        s_list = [str(x[0]) for x in X]

    feats = []
    country_keywords = r"\b(uk|usa|united states|israel|iran|yemen|ukraine|poland|italy|spain|germany|france|belgium|portugal|canada|india|turkey|brazil|saudi arabia|saudi|uae|emirates|russia|china|japan)\b"
    domain_extensions = r"\.(uk|us|de|it|fr|es|ua|in|br|il|sa|ca|ir|ye|cn|jp|ru|ae|ch)\b"

    for s in s_list:
        s_low = s.lower()
        feats.append([
            len(s),
            len(re.findall(country_keywords, s_low)),
            len(re.findall(domain_extensions, s_low)),
        ])

    return csr_matrix(np.asarray(feats, dtype=float))