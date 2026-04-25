import ast
import re
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix


def parse_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        try:
            return ast.literal_eval(x)
        except Exception:
            return []
    return []


def clean_and_normalize(labs):
    if not isinstance(labs, list):
        return []
    labs = [l for l in labs if str(l).lower() != "undefined"]
    labs = [str(l).strip().lower() for l in labs]
    labs = list(dict.fromkeys(labs))
    return labs


def merge_activity_classes(labs):
    """
    Dal notebook:
    recruitment + fundraising -> community_support
    """
    if not isinstance(labs, list):
        return []

    new_labs = []
    for lab in labs:
        lab = str(lab).strip().lower()
        if lab in ["recruitment", "fundraising"]:
            new_labs.append("community_support")
        else:
            new_labs.append(lab)

    new_labs = [l for l in new_labs if l != "undefined"]
    return list(dict.fromkeys(new_labs))


def clean_text_for_inference(text: str) -> str:
    if text is None or pd.isna(text):
        return ""
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def meta_features_df(X):
    """
    Notebook activity:
    5 meta-features
    - lunghezza messaggio
    - numero link
    - flag CVE
    - flag onion
    - numero numeri
    """
    if hasattr(X, "iloc"):
        s_list = X.iloc[:, 0].astype(str).tolist()
    else:
        s_list = [str(x[0]) for x in X]

    feats = []
    for s in s_list:
        s_low = s.lower()
        feats.append([
            len(s),
            len(re.findall(r"http|www\.", s_low)),
            int("cve-" in s_low),
            int(".onion" in s_low),
            len(re.findall(r"\b\d+\b", s)),
        ])

    return csr_matrix(np.asarray(feats, dtype=float))