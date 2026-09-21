"""Telos-X Root."""
"""Telos-X package metadata."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("telos-x")
except PackageNotFoundError:
    # Source checkouts are importable before the package is installed.
    __version__ = "0.1.0"


__all__ = ["__version__"]
