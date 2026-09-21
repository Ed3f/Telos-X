from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List, Optional

from telos_x.ai.activity.predictor import ActivityPredictor
from telos_x.ai.attack_type.predictor import AttackTypePredictor
from telos_x.ai.target_nation.predictor import TargetNationPredictor

from telos_x.ai.decision_engine import DecisionEngine
from telos_x.ai.risk_scoring import RiskScorer


logger = logging.getLogger("TelegramExplorer")


class TelosXAIAnalysis:
    """
    Orchestratore della pipeline AI di Telos-X.

    Flusso:

        testo
          ↓
        Logistic Regression
          ├─ Activity
          ├─ Attack Type
          └─ Target Nation
          ↓
        DecisionEngine
          ↓
        escalation necessaria?
          ├─ no  → resta LR
          └─ sì  → BERT opzionale
          ↓
        merge LR / BERT
          ↓
        RiskScorer
          ↓
        risultato finale

    Principi:
    - LR viene sempre eseguito;
    - BERT è opzionale;
    - BERT non può interrompere la pipeline LR;
    - BERT viene eseguito solo quando il DecisionEngine
      richiede escalation;
    - escalated_to_bert è True solo se almeno un predictor BERT
      ha realmente prodotto un risultato.
    """

    def __init__(self) -> None:
        # =========================================================
        # 1. LOGISTIC REGRESSION
        # =========================================================

        # I modelli LR costituiscono il primo livello della pipeline
        # e devono essere sempre disponibili.
        self.activity = ActivityPredictor()
        self.attack_type = AttackTypePredictor()
        self.target_nation = TargetNationPredictor()

        # =========================================================
        # 2. BERT - SECONDO LIVELLO OPZIONALE
        # =========================================================

        # Ogni predictor viene inizializzato separatamente.
        #
        # Un modello BERT mancante/corrotto non deve impedire
        # l'utilizzo degli altri predictor e soprattutto non deve
        # disabilitare Logistic Regression.
        self.activity_bert = self._safe_init_bert(
            "telos_x.ai.activity.bert_predictor",
            "ActivityBertPredictor",
        )

        self.attack_type_bert = self._safe_init_bert(
            "telos_x.ai.attack_type.bert_predictor",
            "AttackTypeBertPredictor",
        )

        self.target_nation_bert = self._safe_init_bert(
            "telos_x.ai.target_nation.bert_predictor",
            "TargetNationBertPredictor",
        )

        # =========================================================
        # 3. DECISION / RISK
        # =========================================================

        self.decision_engine = DecisionEngine()
        self.risk_scorer = RiskScorer()

    # =============================================================
    # BERT SAFE INITIALIZATION
    # =============================================================

    @staticmethod
    def _safe_init_bert(
        module_name: str,
        class_name: str,
    ) -> Optional[Any]:
        """
        Inizializza un predictor BERT senza permettere che un errore
        interrompa l'intera pipeline AI.

        Restituisce None se:
        - il modello non esiste;
        - mancano tokenizer/artifact;
        - il predictor è disabilitato;
        - il caricamento del modello fallisce;
        - CUDA o altre dipendenze provocano un errore.
        """

        try:
            predictor_cls = getattr(
                importlib.import_module(module_name),
                class_name,
            )
            predictor = predictor_cls()

            # I predictor BERT possono essere costruiti ma risultare
            # intenzionalmente disabilitati quando il modello non esiste.
            if not getattr(
                predictor,
                "enabled",
                True,
            ):
                logger.warning(
                    "[AI] BERT predictor unavailable/disabled: %s",
                    class_name,
                )

                return None

            logger.info(
                "[AI] BERT predictor initialized: %s",
                class_name,
            )

            return predictor

        except (ImportError, ModuleNotFoundError) as exc:
            logger.warning(
                "[AI] Optional BERT predictor unavailable (%s): %s",
                class_name,
                exc,
            )
            return None
        except Exception:
            logger.exception(
                "[AI] Unable to initialize BERT predictor %s. "
                "Logistic Regression will remain available.",
                class_name,
            )

            return None

    # =============================================================
    # SAFE BERT INFERENCE
    # =============================================================

    @staticmethod
    def _safe_bert_predict(
        predictor: Optional[Any],
        text: str,
        task_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Esegue l'inferenza BERT in modo sicuro.

        Se BERT non è disponibile oppure predict() genera
        un'eccezione, viene restituito None.

        Il risultato LR potrà quindi essere mantenuto.
        """

        if predictor is None:
            return None

        try:
            result = predictor.predict(text)

            if result is None:
                logger.debug(
                    "[AI] BERT returned no result for task '%s'.",
                    task_name,
                )

                return None

            return result

        except Exception:
            logger.exception(
                "[AI] BERT inference failed for task '%s'. "
                "Keeping Logistic Regression result.",
                task_name,
            )

            return None

    # =============================================================
    # LR / BERT MERGE
    # =============================================================

    def _merge_task_result(
        self,
        lr_result: Dict[str, Any],
        bert_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Unisce il risultato Logistic Regression con quello BERT.

        Regole:

        1. BERT non eseguito / risultato None
           -> resta LR.

        2. BERT eseguito ma nessuna label accettata
           -> resta LR.

        3. LR non aveva label accettate, BERT sì
           -> usa BERT.

        4. Entrambi hanno label accettate
           -> viene utilizzato il risultato con top_score maggiore.
        """

        # ---------------------------------------------------------
        # 1. BERT non disponibile / non eseguito
        # ---------------------------------------------------------

        if not bert_result:
            result = dict(lr_result)
            result["source_model"] = "lr"

            return result

        # ---------------------------------------------------------
        # 2. Label accettate
        # ---------------------------------------------------------

        lr_labels = (
            lr_result.get("labels")
            or []
        )

        bert_labels = (
            bert_result.get("labels")
            or []
        )

        # ---------------------------------------------------------
        # 3. BERT non ha accettato nessuna classificazione
        # ---------------------------------------------------------

        if not bert_labels:
            result = dict(lr_result)
            result["source_model"] = "lr"

            return result

        # ---------------------------------------------------------
        # 4. LR non aveva label, BERT invece sì
        # ---------------------------------------------------------

        if not lr_labels:
            result = dict(bert_result)
            result["source_model"] = "bert"

            return result

        # ---------------------------------------------------------
        # 5. Entrambi hanno label valide: confronto confidence
        # ---------------------------------------------------------

        try:
            lr_score = float(
                lr_result.get("top_score")
                or 0.0
            )

        except (
            TypeError,
            ValueError,
        ):
            lr_score = 0.0

        try:
            bert_score = float(
                bert_result.get("top_score")
                or 0.0
            )

        except (
            TypeError,
            ValueError,
        ):
            bert_score = 0.0

        # ---------------------------------------------------------
        # 6. Vince BERT se ha confidence almeno pari a LR
        # ---------------------------------------------------------

        if bert_score >= lr_score:
            result = dict(bert_result)
            result["source_model"] = "bert"

            return result

        # ---------------------------------------------------------
        # 7. Altrimenti manteniamo LR
        # ---------------------------------------------------------

        result = dict(lr_result)
        result["source_model"] = "lr"

        return result

    # =============================================================
    # MAIN ANALYSIS
    # =============================================================

    def analyze_message(
        self,
        text: str,
        signal_hits: Optional[
            List[Dict[str, Any]]
        ] = None,
    ) -> Dict[str, Any]:
        """
        Analizza un messaggio tramite la pipeline CTI AI.

        LR viene sempre eseguito.

        BERT viene eseguito solo se DecisionEngine.should_escalate
        restituisce True.
        """

        signal_hits = signal_hits or []

        # =========================================================
        # 1. LOGISTIC REGRESSION
        # =========================================================

        lr_result: Dict[
            str,
            Dict[str, Any],
        ] = {
            "activity": self.activity.predict(
                text
            ),

            "attack_type": (
                self.attack_type.predict(
                    text
                )
            ),

            "target_nation": (
                self.target_nation.predict(
                    text
                )
            ),
        }

        # =========================================================
        # 2. DECISION ENGINE
        # =========================================================

        decision = (
            self.decision_engine.decide(
                text=text,
                lr_result=lr_result,
                signal_hits=signal_hits,
            )
        )

        # =========================================================
        # 3. RISULTATO INIZIALE = LR
        # =========================================================

        final_result: Dict[
            str,
            Dict[str, Any],
        ] = {
            "activity": dict(
                lr_result["activity"]
            ),

            "attack_type": dict(
                lr_result["attack_type"]
            ),

            "target_nation": dict(
                lr_result["target_nation"]
            ),
        }

        final_result[
            "activity"
        ]["source_model"] = "lr"

        final_result[
            "attack_type"
        ]["source_model"] = "lr"

        final_result[
            "target_nation"
        ]["source_model"] = "lr"

        # =========================================================
        # 4. BERT RESULTS
        # =========================================================

        # Di default BERT non è stato eseguito.
        bert_results: Dict[
            str,
            Optional[Dict[str, Any]],
        ] = {
            "activity": None,
            "attack_type": None,
            "target_nation": None,
        }

        # =========================================================
        # 5. ESCALATION
        # =========================================================

        if decision.should_escalate:

            logger.debug(
                "[AI] Message escalated to BERT. Reasons: %s",
                decision.reasons,
            )

            bert_results = {
                "activity": (
                    self._safe_bert_predict(
                        self.activity_bert,
                        text,
                        "activity",
                    )
                ),

                "attack_type": (
                    self._safe_bert_predict(
                        self.attack_type_bert,
                        text,
                        "attack_type",
                    )
                ),

                "target_nation": (
                    self._safe_bert_predict(
                        self.target_nation_bert,
                        text,
                        "target_nation",
                    )
                ),
            }

            # =====================================================
            # 6. MERGE LR / BERT
            # =====================================================

            final_result["activity"] = (
                self._merge_task_result(
                    lr_result["activity"],
                    bert_results["activity"],
                )
            )

            final_result["attack_type"] = (
                self._merge_task_result(
                    lr_result["attack_type"],
                    bert_results["attack_type"],
                )
            )

            final_result["target_nation"] = (
                self._merge_task_result(
                    lr_result["target_nation"],
                    bert_results["target_nation"],
                )
            )

        # =========================================================
        # 7. BERT REALMENTE ESEGUITO?
        # =========================================================

        # IMPORTANTE:
        #
        # decision.should_escalate indica soltanto che il
        # DecisionEngine HA RICHIESTO l'escalation.
        #
        # Non significa che BERT fosse disponibile.
        #
        # Questo flag diventa True solamente quando almeno
        # un predictor BERT ha prodotto realmente un risultato.
        escalated_to_bert = any(
            result is not None
            for result in bert_results.values()
        )

        # =========================================================
        # 8. RISK SCORING
        # =========================================================

        risk_meta = self.risk_scorer.score(
            analysis=final_result,
            signal_hits=signal_hits,
            escalated_to_bert=(
                escalated_to_bert
            ),
        )

        # =========================================================
        # 9. FINDER HIT IDS
        # =========================================================

        # Non assumiamo che ogni hit possieda necessariamente "id".
        rule_hit_ids = [
            str(hit.get("id"))
            for hit in signal_hits
            if hit.get("id") is not None
        ]

        # =========================================================
        # 10. META
        # =========================================================

        final_result["meta"] = {
            # True solamente quando almeno un BERT è stato
            # realmente eseguito.
            "escalated_to_bert": (
                escalated_to_bert
            ),

            # Indica invece che il DecisionEngine aveva richiesto
            # l'approfondimento, anche se BERT non era disponibile.
            "bert_escalation_requested": (
                decision.should_escalate
            ),

            "escalation_reasons": (
                list(
                    dict.fromkeys(
                        decision.reasons
                    )
                )
            ),

            "rule_hits_count": len(
                signal_hits
            ),

            "rule_hit_ids": (
                rule_hit_ids
            ),

            **risk_meta,
        }

        return final_result
