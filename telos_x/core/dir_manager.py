"""Directory Manager."""

from pathlib import Path

from telos_x.paths import resolve_project_path


class DirectoryManagerUtils:
    """Directory Manager."""

    @staticmethod
    def ensure_dir_struct(path: str) -> None:
        """Ensure That Directory Exists.

        :param path:
        :return:
        """
        target_path = Path(path).expanduser()
        if not target_path.is_absolute():
            target_path = resolve_project_path(target_path)
        target_path.mkdir(parents=True, exist_ok=True)
