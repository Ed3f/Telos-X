"""Discord Notifier."""

from __future__ import annotations

import asyncio
from configparser import SectionProxy
from typing import Any, Dict, Optional

from discord_webhook import DiscordEmbed, DiscordWebhook
from telethon.tl.types import Message

from telos_x.notifier.notifier_base import BaseNotifier


class DiscordNotifier(BaseNotifier):
    """Discord notifier for Telegram and CTI alerts."""

    def __init__(self) -> None:
        """Initialize Discord Notifier."""
        super().__init__()

        self.url: str = ""
        self.only_rule_matches: bool = False

    def configure(
        self,
        url: str,
        config: SectionProxy,
    ) -> None:
        """Configure the notifier."""

        self.url = url

        self.configure_base(
            config=config,
        )

        self.only_rule_matches = config.getboolean(
            "only_rule_matches",
            fallback=False,
        )

    async def send_text(self, text: str) -> None:
        """Send a generic status message through the configured webhook."""
        is_duplicated, _ = self.check_is_duplicated(message=text)
        if is_duplicated:
            return
        webhook = DiscordWebhook(
            url=self.url,
            content=self._truncate(text, 2000),
            rate_limit_retry=True,
        )
        await asyncio.to_thread(webhook.execute)

    async def run(
        self,
        message: Message,
        **kwargs: Any,
    ) -> None:
        """
        Send a Discord notification.

        Supports:
        - realtime Telegram messages
        - batch downloaded messages
        - Finder rule matches
        - AI severity/risk alerts
        - LR/BERT analysis metadata
        """

        # ---------------------------------------------------------
        # 1. Resolve message text
        # ---------------------------------------------------------

        raw_text = (
            kwargs.get("raw_text")
            or getattr(message, "raw_text", None)
            or getattr(message, "message", None)
            or ""
        )

        translated_text = (
            kwargs.get("translation")
            or raw_text
        )

        # ---------------------------------------------------------
        # 2. Duplicate protection
        # ---------------------------------------------------------

        is_duplicated, duplication_tag = self.check_is_duplicated(
            message=raw_text,
        )

        if is_duplicated:
            return

        # ---------------------------------------------------------
        # 3. Rule-only policy
        # ---------------------------------------------------------

        rule_id = kwargs.get("rule_id")

        if self.only_rule_matches and not rule_id:
            return

        # ---------------------------------------------------------
        # 4. Resolve Telegram group safely
        #
        # message.chat may not exist during batch scraping.
        # ---------------------------------------------------------

        group_id = kwargs.get("group_id")

        chat = getattr(
            message,
            "chat",
            None,
        )

        chat_title = getattr(
            chat,
            "title",
            None,
        )

        chat_id = getattr(
            chat,
            "id",
            None,
        )

        if chat_id is None:
            chat_id = group_id

        if chat_title is None:
            if chat_id is not None:
                chat_title = f"Telegram Group {chat_id}"
            else:
                chat_title = "Telegram Group"

        # ---------------------------------------------------------
        # 5. CTI / AI metadata
        # ---------------------------------------------------------

        ai_result: Dict[str, Any] = (
            kwargs.get("ai_result")
            or {}
        )

        meta: Dict[str, Any] = (
            ai_result.get("meta")
            or {}
        )

        activity: Dict[str, Any] = (
            ai_result.get("activity")
            or {}
        )

        attack_type: Dict[str, Any] = (
            ai_result.get("attack_type")
            or {}
        )

        target_nation: Dict[str, Any] = (
            ai_result.get("target_nation")
            or {}
        )

        severity = (
            kwargs.get("severity")
            or meta.get("severity")
            or "low"
        )

        risk_score = kwargs.get("risk_score")

        if risk_score is None:
            risk_score = meta.get(
                "risk_score",
                0.0,
            )

        escalated_to_bert = bool(
            meta.get(
                "escalated_to_bert",
                False,
            )
        )

        escalation_reasons = (
            meta.get("escalation_reasons")
            or []
        )

        rule_hits = (
            kwargs.get("rule_hits")
            or []
        )

        # ---------------------------------------------------------
        # 6. Build Discord webhook
        # ---------------------------------------------------------

        webhook = DiscordWebhook(
            url=self.url,
            rate_limit_retry=True,
        )

        embed = DiscordEmbed(
            title=self._truncate(
                f"{chat_title} ({chat_id})",
                256,
            ),
            description=self._truncate(
                translated_text,
                4096,
            ),
        )

        # ---------------------------------------------------------
        # 7. Telegram metadata
        # ---------------------------------------------------------

        embed.add_embed_field(
            name="Message ID",
            value=str(
                getattr(
                    message,
                    "id",
                    "unknown",
                )
            ),
            inline=True,
        )

        embed.add_embed_field(
            name="Group Name",
            value=self._truncate(
                str(chat_title),
                1024,
            ),
            inline=True,
        )

        embed.add_embed_field(
            name="Group ID",
            value=str(
                chat_id
                if chat_id is not None
                else "unknown"
            ),
            inline=True,
        )

        message_date = getattr(
            message,
            "date",
            None,
        )

        if message_date is not None:
            embed.add_embed_field(
                name="Message Date",
                value=self._truncate(
                    str(message_date),
                    1024,
                ),
                inline=False,
            )

        if duplication_tag:
            embed.add_embed_field(
                name="Tag",
                value=self._truncate(
                    str(duplication_tag),
                    1024,
                ),
                inline=False,
            )

        # ---------------------------------------------------------
        # 8. CTI risk information
        # ---------------------------------------------------------

        embed.add_embed_field(
            name="Severity",
            value=str(severity).upper(),
            inline=True,
        )

        try:
            risk_score_formatted = f"{float(risk_score):.3f}"
        except (TypeError, ValueError):
            risk_score_formatted = str(risk_score)

        embed.add_embed_field(
            name="Risk Score",
            value=risk_score_formatted,
            inline=True,
        )

        embed.add_embed_field(
            name="BERT Escalation",
            value="Yes" if escalated_to_bert else "No",
            inline=True,
        )

        # ---------------------------------------------------------
        # 9. Activity classification
        # ---------------------------------------------------------

        self._add_ai_field(
            embed=embed,
            name="Activity",
            result=activity,
        )

        # ---------------------------------------------------------
        # 10. Attack type classification
        # ---------------------------------------------------------

        self._add_ai_field(
            embed=embed,
            name="Attack Type",
            result=attack_type,
        )

        # ---------------------------------------------------------
        # 11. Target nation classification
        # ---------------------------------------------------------

        self._add_ai_field(
            embed=embed,
            name="Target",
            result=target_nation,
        )

        # ---------------------------------------------------------
        # 12. Decision engine information
        # ---------------------------------------------------------

        if escalation_reasons:
            embed.add_embed_field(
                name="Escalation Reasons",
                value=self._truncate(
                    ", ".join(
                        str(reason)
                        for reason in escalation_reasons
                    ),
                    1024,
                ),
                inline=False,
            )

        # ---------------------------------------------------------
        # 13. Finder information
        # ---------------------------------------------------------

        if rule_id:
            embed.add_embed_field(
                name="Rule ID",
                value=self._truncate(
                    str(rule_id),
                    1024,
                ),
                inline=False,
            )

        if rule_hits:
            rule_names = []

            for hit in rule_hits:
                if not isinstance(hit, dict):
                    continue

                hit_id = hit.get("id")

                if hit_id:
                    rule_names.append(
                        str(hit_id)
                    )

            if rule_names:
                embed.add_embed_field(
                    name="Finder Hits",
                    value=self._truncate(
                        "\n".join(rule_names),
                        1024,
                    ),
                    inline=False,
                )

            matching_hit = self._find_rule_hit(
                rule_id=rule_id,
                rule_hits=rule_hits,
            )

            if matching_hit:
                response = matching_hit.get(
                    "response"
                )

                if response:
                    embed.add_embed_field(
                        name="Finder Response",
                        value=self._truncate(
                            str(response),
                            1024,
                        ),
                        inline=False,
                    )

                severity_hint = matching_hit.get(
                    "severity_hint"
                )

                if severity_hint:
                    embed.add_embed_field(
                        name="Rule Severity Hint",
                        value=str(
                            severity_hint
                        ).upper(),
                        inline=True,
                    )

        # ---------------------------------------------------------
        # 14. Original text
        #
        # Only show it when translation actually differs.
        # ---------------------------------------------------------

        if (
            raw_text
            and translated_text
            and raw_text.strip()
            != translated_text.strip()
        ):
            embed.add_embed_field(
                name="Original Message",
                value=self._truncate(
                    raw_text,
                    1024,
                ),
                inline=False,
            )

        webhook.add_embed(
            embed,
        )

        # discord_webhook.execute() is synchronous.
        # Running it in a worker thread prevents blocking Telethon's
        # asyncio event loop.
        await asyncio.to_thread(
            webhook.execute,
        )

    # =============================================================
    # Helpers
    # =============================================================

    @staticmethod
    def _add_ai_field(
        *,
        embed: DiscordEmbed,
        name: str,
        result: Dict[str, Any],
    ) -> None:
        """Add a classifier result to the Discord embed."""

        if not result:
            return

        top_label = result.get(
            "top_label"
        )

        top_score = result.get(
            "top_score"
        )

        source_model = result.get(
            "source_model"
        )

        if top_label is None:
            return

        value_parts = [
            str(top_label),
        ]

        if top_score is not None:
            try:
                value_parts.append(
                    f"score={float(top_score):.3f}"
                )
            except (TypeError, ValueError):
                value_parts.append(
                    f"score={top_score}"
                )

        if source_model:
            value_parts.append(
                f"model={source_model}"
            )

        value = "\n".join(
            value_parts
        )

        embed.add_embed_field(
            name=name,
            value=DiscordNotifier._truncate(
                value,
                1024,
            ),
            inline=True,
        )

    @staticmethod
    def _find_rule_hit(
        *,
        rule_id: Optional[str],
        rule_hits: list,
    ) -> Optional[Dict[str, Any]]:
        """Return Finder information related to the active rule."""

        if not rule_id:
            return None

        for hit in rule_hits:
            if not isinstance(
                hit,
                dict,
            ):
                continue

            if hit.get("id") == rule_id:
                return hit

        return None

    @staticmethod
    def _truncate(
        value: Any,
        max_length: int,
    ) -> str:
        """Safely truncate text to Discord embed limits."""

        if value is None:
            return ""

        text = str(value)

        if len(text) <= max_length:
            return text

        if max_length <= 3:
            return text[:max_length]

        return (
            text[: max_length - 3]
            + "..."
        )
