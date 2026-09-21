from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class RiskScorer:
    """
    Produce un risk score [0, 1] a partire da classificazioni
    effettivamente accettate e segnali Finder.
    """

    MIN_RISK_CONFIDENCE = 0.60

    ATTACK_BOOST = {
        "data_leak": 0.22,
        "ddos": 0.18,
        "malware": 0.20,
        "website_defacement": 0.12,
    }

    ACTIVITY_BOOST = {
        "attack_claim": 0.18,
        "attack_coordination": 0.22,
        "community_support": 0.03,
        "marketplace_services": 0.12,
        "propaganda": 0.04,
        "target_listing": 0.10,
        "tool_sharing": 0.08,
    }

    SIGNAL_BOOST = {
        "low": 0.03,
        "medium": 0.08,
        "high": 0.15,
        "critical": 0.25,
    }

    @classmethod
    def _accepted_top(
        cls,
        result: Dict[str, Any],
    ) -> Tuple[Optional[str], float]:

        labels = set(result.get("labels") or [])
        top_label = result.get("top_label")

        try:
            top_score = float(result.get("top_score") or 0.0)
        except (TypeError, ValueError):
            top_score = 0.0

        if top_label is None:
            return None, 0.0

        if top_label not in labels:
            return None, 0.0

        if top_score < cls.MIN_RISK_CONFIDENCE:
            return None, 0.0

        return str(top_label), max(0.0, min(1.0, top_score))

    def score(
        self,
        *,
        analysis: Dict[str, Dict[str, Any]],
        signal_hits: List[Dict[str, Any]] | None = None,
        escalated_to_bert: bool = False,
    ) -> Dict[str, Any]:

        _ = escalated_to_bert

        signal_hits = signal_hits or []
        valid_signal_hits = [
            hit
            for hit in signal_hits
            if isinstance(hit, dict) and bool(hit)
        ]
        analysis = analysis or {}

        activity = analysis.get("activity", {})
        attack = analysis.get("attack_type", {})

        activity_label, activity_score = self._accepted_top(activity)
        attack_label, attack_score = self._accepted_top(attack)

        base = 0.0

        base += 0.30 * activity_score
        base += 0.45 * attack_score

        if activity_label:
            base += (
                self.ACTIVITY_BOOST.get(activity_label, 0.0)
                * activity_score
            )

        if attack_label:
            base += (
                self.ATTACK_BOOST.get(attack_label, 0.0)
                * attack_score
            )

        signal_bonus = 0.0

        for hit in valid_signal_hits:
            severity_hint = str(
                hit.get("severity_hint") or "medium"
            ).lower()

            signal_bonus += self.SIGNAL_BOOST.get(
                severity_hint,
                0.08,
            )

        base += min(signal_bonus, 0.25)

        risk_score = max(
            0.0,
            min(1.0, round(base, 4)),
        )

        if risk_score >= 0.85:
            severity = "critical"
        elif risk_score >= 0.65:
            severity = "high"
        elif risk_score >= 0.40:
            severity = "medium"
        else:
            severity = "low"

        alert_recommended = (
            severity in {"medium", "high", "critical"}
            or bool(valid_signal_hits)
        )

        return {
            "risk_score": risk_score,
            "severity": severity,
            "alert_recommended": alert_recommended,
        }
