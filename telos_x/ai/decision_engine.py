from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class EscalationDecision:
    should_escalate: bool
    reasons: List[str] = field(default_factory=list)


class DecisionEngine:
    """
    Decide quando il risultato LR merita approfondimento BERT.
    """

    CRITICAL_ACTIVITY = {
        "attack_claim",
        "attack_coordination",
    }

    CRITICAL_ATTACK = {
        "data_leak",
        "ddos",
        "malware",
        "website_defacement",
    }

    CRITICAL_KEYWORDS = (
        "full access",
        "database dump",
        "leak",
        "breach",
        "stealer",
        "ransomware",
        "0day",
        "zero-day",
        "exploit",
    )

    def __init__(
        self,
        low_confidence_threshold: float = 0.65,
        ambiguity_gap_threshold: float = 0.08,
        critical_label_threshold: float = 0.60,
        escalate_on_rule_hits: bool = True,
    ) -> None:

        self.low_confidence_threshold = low_confidence_threshold
        self.ambiguity_gap_threshold = ambiguity_gap_threshold
        self.critical_label_threshold = critical_label_threshold
        self.escalate_on_rule_hits = escalate_on_rule_hits

    @staticmethod
    def _has_accepted_labels(
        result: Dict[str, Any],
    ) -> bool:
        return bool(result.get("labels"))

    def _accepted_critical_label(
        self,
        result: Dict[str, Any],
        critical_labels: set[str],
    ) -> bool:

        labels = set(result.get("labels") or [])
        top_label = result.get("top_label")

        try:
            top_score = float(result.get("top_score") or 0.0)
        except (TypeError, ValueError):
            return False

        return (
            top_label in labels
            and top_label in critical_labels
            and top_score >= self.critical_label_threshold
        )

    def decide(
        self,
        *,
        text: str,
        lr_result: Dict[str, Dict[str, Any]],
        signal_hits: List[Dict[str, Any]] | None = None,
    ) -> EscalationDecision:
        """
        Decide se il risultato dei classificatori LR deve essere
        approfondito tramite BERT.

        L'escalation avviene quando:
        - Activity o Attack Type non hanno nessuna label accettata;
        - una classificazione accettata ha confidence bassa;
        - due classi hanno score molto vicini;
        - viene accettata una label critica;
        - il Finder produce almeno un signal hit;
        - il testo contiene keyword considerate critiche.

        Target Nation senza label accettate NON causa automaticamente
        escalation, perché molti messaggi CTI possono non contenere
        riferimenti geografici.
        """

        reasons: List[str] = []
        signal_hits = signal_hits or []

        activity = lr_result.get("activity") or {}
        attack = lr_result.get("attack_type") or {}
        nation = lr_result.get("target_nation") or {}

        # =========================================================
        # 1. NESSUNA LABEL ACCETTATA
        # =========================================================
        #
        # Se Activity o Attack Type non riescono ad accettare
        # nessuna classificazione, il messaggio è abbastanza
        # incerto da richiedere approfondimento BERT.
        #
        # Target Nation viene volutamente escluso da questa regola.
        # Un messaggio può infatti essere rilevante dal punto di vista
        # CTI senza contenere alcun target geografico.
        # =========================================================

        for task_name, result in (
            ("activity", activity),
            ("attack_type", attack),
        ):
            if not self._has_accepted_labels(result):
                reasons.append(
                    f"no_accepted_label:{task_name}"
                )

        # =========================================================
        # 2. LOW CONFIDENCE
        # =========================================================
        #
        # Questa regola viene valutata solo quando almeno una label
        # è stata realmente accettata dal classificatore.
        # =========================================================

        for task_name, result in (
            ("activity", activity),
            ("attack_type", attack),
            ("target_nation", nation),
        ):
            if not self._has_accepted_labels(result):
                continue

            try:
                top_score = float(
                    result.get("top_score") or 0.0
                )
            except (TypeError, ValueError):
                top_score = 0.0

            if top_score < self.low_confidence_threshold:
                reasons.append(
                    f"low_confidence:{task_name}"
                )

        # =========================================================
        # 3. AMBIGUITÀ TRA LE CLASSI
        # =========================================================
        #
        # Se i due score più alti sono molto vicini, LR potrebbe
        # essere incerto sulla classificazione migliore.
        # =========================================================

        for task_name, result in (
            ("activity", activity),
            ("attack_type", attack),
            ("target_nation", nation),
        ):
            if not self._has_accepted_labels(result):
                continue

            raw_scores = (
                result.get("scores") or {}
            )

            scores: List[float] = []

            for value in raw_scores.values():
                try:
                    scores.append(
                        float(value)
                    )
                except (TypeError, ValueError):
                    continue

            scores.sort(
                reverse=True
            )

            if (
                len(scores) >= 2
                and scores[0] >= 0.50
                and (
                    scores[0] - scores[1]
                    <= self.ambiguity_gap_threshold
                )
            ):
                reasons.append(
                    f"ambiguous:{task_name}"
                )

        # =========================================================
        # 4. LABEL CRITICHE
        # =========================================================
        #
        # Una label critica causa escalation solo se:
        #
        # - è realmente presente tra le label accettate;
        # - coincide con top_label;
        # - supera critical_label_threshold.
        # =========================================================

        if self._accepted_critical_label(
            activity,
            self.CRITICAL_ACTIVITY,
        ):
            reasons.append(
                "critical_activity_label"
            )

        if self._accepted_critical_label(
            attack,
            self.CRITICAL_ATTACK,
        ):
            reasons.append(
                "critical_attack_label"
            )

        # =========================================================
        # 5. FINDER SIGNAL
        # =========================================================

        if (
            self.escalate_on_rule_hits
            and signal_hits
        ):
            reasons.append(
                "finder_signal_hit"
            )

        # =========================================================
        # 6. KEYWORD CRITICHE
        # =========================================================

        text_lower = (
            text or ""
        ).lower()

        if any(
            keyword in text_lower
            for keyword in self.CRITICAL_KEYWORDS
        ):
            reasons.append(
                "critical_keyword"
            )

        # =========================================================
        # 7. RIMOZIONE EVENTUALI DUPLICATI
        # =========================================================

        reasons = list(
            dict.fromkeys(reasons)
        )

        # =========================================================
        # 8. DECISIONE FINALE
        # =========================================================

        return EscalationDecision(
            should_escalate=bool(reasons),
            reasons=reasons,
        )