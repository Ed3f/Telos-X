"""Operating system statistics utilities."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict

import psutil


def get_disk_stats(
    path: str,
) -> Dict[str, float]:
    """
    Return disk usage statistics for the filesystem containing ``path``.

    Values are expressed in GB, except ``percent_used``.
    """

    target_path = Path(
        path
    ).expanduser()

    # If data_path does not exist yet, use its nearest existing parent.
    while not target_path.exists() and target_path != target_path.parent:
        target_path = target_path.parent

    usage = shutil.disk_usage(
        target_path
    )

    total_gb = (
        usage.total
        / (1024 ** 3)
    )

    used_gb = (
        usage.used
        / (1024 ** 3)
    )

    free_gb = (
        usage.free
        / (1024 ** 3)
    )

    percent_used = (
        (
            usage.used
            / usage.total
        )
        * 100
        if usage.total
        else 0.0
    )

    return {
        "total_gb": round(
            total_gb,
            2,
        ),
        "used_gb": round(
            used_gb,
            2,
        ),
        "free_gb": round(
            free_gb,
            2,
        ),
        "percent_used": round(
            percent_used,
            2,
        ),
    }


def get_system_stats(
    data_path: str,
) -> Dict:
    """
    Return the principal system statistics used by Telos-X.
    """

    memory = (
        psutil.virtual_memory()
    )

    return {
        "disk": get_disk_stats(
            data_path
        ),

        "memory": {
            "total_gb": round(
                memory.total
                / (1024 ** 3),
                2,
            ),

            "available_gb": round(
                memory.available
                / (1024 ** 3),
                2,
            ),

            "percent_used": float(
                memory.percent
            ),
        },

        "cpu_percent": float(
            psutil.cpu_percent(
                interval=None
            )
        ),
    }
