from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class EscalationDecision:
    should_escalate: bool
    reasons: List[str] = field(default_factory=list)


class DecisionEngine:
    CRITICAL_ACTIVITY = {
        "data_leak",
        "initial_access_sale",
        "credential_sale",
        "ransomware",
    }

    CRITICAL_ATTACK = {
        "malware",
        "ransomware",
        "exploit",
        "phishing",
    }

    CRITICAL_KEYWORDS = (
        "full access",
        "database dump",
        "leak",
        "breach",
        "stealer",
        "ransomware",
        "0day",
        "exploit",
    )

    def __init__(
        self,
        low_confidence_threshold: float = 0.65,
        ambiguity_gap_threshold: float = 0.08,
        escalate_on_rule_hits: bool = True,
    ) -> None:
        self.low_confidence_threshold = low_confidence_threshold
        self.ambiguity_gap_threshold = ambiguity_gap_threshold
        self.escalate_on_rule_hits = escalate_on_rule_hits

    def decide(
        self,
        *,
        text: str,
        lr_result: Dict[str, Dict[str, Any]],
        signal_hits: List[Dict[str, Any]] | None = None,
    ) -> EscalationDecision:
        reasons: List[str] = []
        signal_hits = signal_hits or []

        activity = lr_result.get("activity", {})
        attack = lr_result.get("attack_type", {})
        nation = lr_result.get("target_nation", {})

        for task_name, result in (
            ("activity", activity),
            ("attack_type", attack),
            ("target_nation", nation),
        ):
            top_score = float(result.get("top_score") or 0.0)
            if top_score < self.low_confidence_threshold:
                reasons.append(f"low_confidence:{task_name}")

        for task_name, result in (
            ("activity", activity),
            ("attack_type", attack),
            ("target_nation", nation),
        ):
            scores = sorted(
                [float(v) for v in (result.get("scores") or {}).values()],
                reverse=True,
            )
            if len(scores) >= 2 and (scores[0] - scores[1]) <= self.ambiguity_gap_threshold:
                reasons.append(f"ambiguous:{task_name}")

        if activity.get("top_label") in self.CRITICAL_ACTIVITY:
            reasons.append("critical_activity_label")

        if attack.get("top_label") in self.CRITICAL_ATTACK:
            reasons.append("critical_attack_label")

        if self.escalate_on_rule_hits and signal_hits:
            reasons.append("finder_signal_hit")

        text_lower = (text or "").lower()
        if any(k in text_lower for k in self.CRITICAL_KEYWORDS):
            reasons.append("critical_keyword")

        return EscalationDecision(
            should_escalate=bool(reasons),
            reasons=reasons,
        )