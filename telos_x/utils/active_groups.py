"""Utilities for checking monitored Telegram groups."""

from __future__ import annotations

import asyncio
from typing import Dict, Iterable

from telethon import TelegramClient


async def check_group_status(
    client: TelegramClient,
    group_id: int,
) -> Dict:
    """
    Check whether a Telegram group/channel is reachable.
    """

    try:
        entity = await client.get_entity(
            group_id
        )

        return {
            "group_id": group_id,
            "name": (
                getattr(
                    entity,
                    "title",
                    None,
                )
                or getattr(
                    entity,
                    "username",
                    None,
                )
                or str(group_id)
            ),
            "status": "up",
            "error": None,
        }

    except Exception as exc:
        return {
            "group_id": group_id,
            "name": str(
                group_id
            ),
            "status": "down",
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }


async def get_active_groups(
    client: TelegramClient,
    group_ids: Iterable[int],
) -> Dict:
    """
    Check all configured Telegram groups concurrently.
    """

    tasks = [
        check_group_status(
            client,
            int(group_id),
        )
        for group_id in group_ids
    ]

    results = (
        await asyncio.gather(
            *tasks
        )
    )

    up = [
        result
        for result in results
        if result[
            "status"
        ] == "up"
    ]

    down = [
        result
        for result in results
        if result[
            "status"
        ] == "down"
    ]

    return {
        "total": len(
            results
        ),

        "up_count": len(
            up
        ),

        "down_count": len(
            down
        ),

        "up": up,
        "down": down,
    }