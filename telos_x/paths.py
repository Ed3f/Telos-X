"""Deterministic paths used by Telos-X runtime components."""

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
_PROJECT_GROUPS_FILE = PROJECT_ROOT / "groups.csv"
_PACKAGED_GROUPS_FILE = PACKAGE_ROOT / "groups.csv"
DEFAULT_GROUPS_FILE = (
    _PROJECT_GROUPS_FILE
    if _PROJECT_GROUPS_FILE.exists()
    else _PACKAGED_GROUPS_FILE
)
REPORT_TEMPLATES = PACKAGE_ROOT / "report_templates"


def resolve_project_path(value: str | Path) -> Path:
    """Resolve a configured path without depending on the current directory."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()
