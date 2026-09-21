"""Compatibility aliases for LR artifacts serialized before package renaming."""

from importlib import import_module
import sys


_LEGACY_MODULES = {
    "ai": "telos_x.ai",
    "ai.activity": "telos_x.ai.activity",
    "ai.activity.preprocessing": "telos_x.ai.activity.preprocessing",
    "ai.attack_type": "telos_x.ai.attack_type",
    "ai.attack_type.preprocessing": "telos_x.ai.attack_type.preprocessing",
    "ai.target_nation": "telos_x.ai.target_nation",
    "ai.target_nation.preprocessing": "telos_x.ai.target_nation.preprocessing",
}


def install_legacy_joblib_aliases() -> None:
    """Expose only the historical module names required by shipped joblibs."""
    for legacy_name, current_name in _LEGACY_MODULES.items():
        sys.modules.setdefault(legacy_name, import_module(current_name))


def apply_sklearn_artifact_compatibility(model: object) -> object:
    """Repair the one known 1.8-artifact/1.7-runtime state difference.

    Scikit-learn 1.8 removed ``LogisticRegression.multi_class`` from newly
    serialized estimators, while the Python-3.10-compatible 1.7 prediction
    path still reads it.  Restoring 1.7's ``"auto"`` default is equivalent to
    the fitted binary estimators' original behavior and keeps the committed
    artifacts usable across Telos-X's declared Python range.
    """
    named_steps = getattr(model, "named_steps", {})
    classifier = named_steps.get("clf") if hasattr(named_steps, "get") else None
    for estimator in getattr(classifier, "estimators_", ()):
        if (
            type(estimator).__name__ == "LogisticRegression"
            and not hasattr(estimator, "multi_class")
        ):
            estimator.multi_class = "auto"
    return model
