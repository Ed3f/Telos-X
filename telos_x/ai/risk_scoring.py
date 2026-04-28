from __future__ import annotations

from typing import Any, Dict, List


class RiskScorer:
    ATTACK_BOOST = {
        "ransomware": 0.25,
        "exploit": 0.20,
        "malware": 0.18,
        "phishing": 0.12,
    }

    ACTIVITY_BOOST = {
        "data_leak": 0.22,
        "initial_access_sale": 0.22,
        "credential_sale": 0.18,
        "ransomware": 0.20,
    }

    def score(
        self,
        *,
        analysis: Dict[str, Dict[str, Any]],
        signal_hits: List[Dict[str, Any]] | None = None,
        escalated_to_bert: bool = False,
    ) -> Dict[str, Any]:
        signal_hits = signal_hits or []

        activity = analysis.get("activity", {})
        attack = analysis.get("attack_type", {})
        nation = analysis.get("target_nation", {})

        base = 0.0
        base += 0.35 * float(activity.get("top_score") or 0.0)
        base += 0.45 * float(attack.get("top_score") or 0.0)
        base += 0.10 * float(nation.get("top_score") or 0.0)

        base += self.ACTIVITY_BOOST.get(activity.get("top_label"), 0.0)
        base += self.ATTACK_BOOST.get(attack.get("top_label"), 0.0)

        if signal_hits:
            base += min(0.25, 0.08 * len(signal_hits))

        if escalated_to_bert:
            base += 0.05

        risk_score = max(0.0, min(1.0, round(base, 4)))

        if risk_score >= 0.85:
            severity = "critical"
        elif risk_score >= 0.65:
            severity = "high"
        elif risk_score >= 0.40:
            severity = "medium"
        else:
            severity = "low"

        alert_recommended = severity in {"high", "critical"} or bool(signal_hits)

        return {
            "risk_score": risk_score,
            "severity": severity,
            "alert_recommended": alert_recommended,
        }