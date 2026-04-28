from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from telos_x.ai.activity.predictor import ActivityPredictor
from telos_x.ai.activity.bert_predictior import ActivityBertPredictor
from telos_x.ai.attack_type.predictor import AttackTypePredictor
from telos_x.ai.attack_type.bert_predictor import AttackTypeBertPredictor
from telos_x.ai.target_nation.predictor import TargetNationPredictor
from telos_x.ai.target_nation.bert_predictor import TargetNationBertPredictor
from telos_x.ai.decision_engine import DecisionEngine
from telos_x.ai.risk_scoring import RiskScorer


class TelosXAIAnalysis:
    """
    CTI orchestrator:
    - LR always executed
    - decision engine decides escalation
    - BERT only on escalation
    - risk scoring + severity
    """

    def __init__(self) -> None:
        self.activity = ActivityPredictor()
        self.attack_type = AttackTypePredictor()
        self.target_nation = TargetNationPredictor()

        self.activity_bert = ActivityBertPredictor()
        self.attack_type_bert = AttackTypeBertPredictor()
        self.target_nation_bert = TargetNationBertPredictor()

        self.decision_engine = DecisionEngine()
        self.risk_scorer = RiskScorer()

    def _merge_task_result(
        self,
        lr_result: Dict[str, Any],
        bert_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not bert_result:
            result = dict(lr_result)
            result["source_model"] = "lr"
            return result

        lr_score = float(lr_result.get("top_score") or 0.0)
        bert_score = float(bert_result.get("top_score") or 0.0)

        if bert_score >= lr_score:
            return dict(bert_result)

        result = dict(lr_result)
        result["source_model"] = "lr"
        return result

    def analyze_message(
        self,
        text: str,
        signal_hits: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        signal_hits = signal_hits or []

        lr_result = {
            "activity": self.activity.predict(text),
            "attack_type": self.attack_type.predict(text),
            "target_nation": self.target_nation.predict(text),
        }

        decision = self.decision_engine.decide(
            text=text,
            lr_result=lr_result,
            signal_hits=signal_hits,
        )

        escalated_to_bert = False

        final_result = {
            "activity": dict(lr_result["activity"]),
            "attack_type": dict(lr_result["attack_type"]),
            "target_nation": dict(lr_result["target_nation"]),
        }
        final_result["activity"]["source_model"] = "lr"
        final_result["attack_type"]["source_model"] = "lr"
        final_result["target_nation"]["source_model"] = "lr"

        if decision.should_escalate:
            escalated_to_bert = True

            final_result["activity"] = self._merge_task_result(
                lr_result["activity"],
                self.activity_bert.predict(text),
            )
            final_result["attack_type"] = self._merge_task_result(
                lr_result["attack_type"],
                self.attack_type_bert.predict(text),
            )
            final_result["target_nation"] = self._merge_task_result(
                lr_result["target_nation"],
                self.target_nation_bert.predict(text),
            )

        risk_meta = self.risk_scorer.score(
            analysis=final_result,
            signal_hits=signal_hits,
            escalated_to_bert=escalated_to_bert,
        )

        final_result["meta"] = {
            "escalated_to_bert": escalated_to_bert,
            "escalation_reasons": decision.reasons,
            "rule_hits_count": len(signal_hits),
            "rule_hit_ids": [hit["id"] for hit in signal_hits],
            **risk_meta,
        }

        return final_result