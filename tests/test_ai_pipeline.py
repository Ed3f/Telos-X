"""Tests for shipped LR artifacts, decision orchestration, and risk scoring."""

import math

import pytest

from telos_x.ai.activity.predictor import ActivityPredictor
from telos_x.ai.attack_type.predictor import AttackTypePredictor
from telos_x.ai.decision_engine import DecisionEngine
from telos_x.ai.risk_scoring import RiskScorer
from telos_x.ai.target_nation.predictor import TargetNationPredictor
from telos_x.ai.telosx_ai_analysis import TelosXAIAnalysis


@pytest.mark.parametrize(
    'predictor_class',
    [ActivityPredictor, AttackTypePredictor, TargetNationPredictor],
)
def test_actual_lr_artifact_loads_and_predicts(predictor_class):
    predictor = predictor_class()
    assert all(
        hasattr(estimator, 'multi_class')
        for estimator in predictor.model.named_steps['clf'].estimators_
    )
    result = predictor.predict('We claim a DDoS attack against a European target')
    assert predictor.labels
    assert set(predictor.thresholds).issubset(set(predictor.labels))
    assert result['top_label'] in predictor.labels
    assert math.isfinite(result['top_score'])
    assert result['scores']


def _task(labels=None, top=None, score=0.0, scores=None):
    return {
        'labels': labels or [],
        'top_label': top,
        'top_score': score,
        'scores': scores or {},
    }


def _lr(activity=None, attack=None, nation=None):
    return {
        'activity': activity or _task(),
        'attack_type': attack or _task(),
        'target_nation': nation or _task(),
    }


def test_decision_engine_benign_accepted_predictions_do_not_escalate():
    accepted_activity = _task(['propaganda'], 'propaganda', 0.9, {'propaganda': 0.9})
    accepted_attack = _task(['other'], 'other', 0.9, {'other': 0.9})
    decision = DecisionEngine().decide(
        text='ordinary statement',
        lr_result=_lr(accepted_activity, accepted_attack),
    )
    assert not decision.should_escalate


@pytest.mark.parametrize(
    'lr_result,text,hits,reason',
    [
        (_lr(), 'ordinary', [], 'no_accepted_label:activity'),
        (
            _lr(
                _task(['propaganda'], 'propaganda', 0.4),
                _task(['other'], 'other', 0.9),
            ),
            'ordinary',
            [],
            'low_confidence:activity',
        ),
        (
            _lr(
                _task(['propaganda'], 'propaganda', 0.7, {'a': 0.7, 'b': 0.66}),
                _task(['other'], 'other', 0.9),
            ),
            'ordinary',
            [],
            'ambiguous:activity',
        ),
        (
            _lr(
                _task(['attack_claim'], 'attack_claim', 0.9),
                _task(['other'], 'other', 0.9),
            ),
            'ordinary',
            [],
            'critical_activity_label',
        ),
        (
            _lr(
                _task(['propaganda'], 'propaganda', 0.9),
                _task(['ddos'], 'ddos', 0.9),
            ),
            'ordinary',
            [],
            'critical_attack_label',
        ),
        (
            _lr(
                _task(['propaganda'], 'propaganda', 0.9),
                _task(['other'], 'other', 0.9),
            ),
            'database dump available',
            [],
            'critical_keyword',
        ),
        (
            _lr(
                _task(['propaganda'], 'propaganda', 0.9),
                _task(['other'], 'other', 0.9),
            ),
            'ordinary',
            [{'id': 'finder'}],
            'finder_signal_hit',
        ),
    ],
)
def test_decision_engine_escalation_reasons(lr_result, text, hits, reason):
    decision = DecisionEngine().decide(text=text, lr_result=lr_result, signal_hits=hits)
    assert decision.should_escalate
    assert reason in decision.reasons


def test_missing_target_nation_alone_does_not_escalate():
    decision = DecisionEngine().decide(
        text='ordinary',
        lr_result=_lr(
            _task(['propaganda'], 'propaganda', 0.9),
            _task(['other'], 'other', 0.9),
            _task(),
        ),
    )
    assert not decision.should_escalate


@pytest.mark.parametrize(
    'analysis,hits,severity',
    [
        (_lr(), [], 'low'),
        (
            _lr(_task(['tool_sharing'], 'tool_sharing', 0.7), _task()),
            [{'severity_hint': 'high'}],
            'medium',
        ),
        (
            _lr(
                _task(['tool_sharing'], 'tool_sharing', 0.7),
                _task(['ddos'], 'ddos', 0.7),
            ),
            [],
            'high',
        ),
        (
            _lr(
                _task(['attack_coordination'], 'attack_coordination', 1.0),
                _task(['data_leak'], 'data_leak', 1.0),
            ),
            [],
            'critical',
        ),
    ],
)
def test_risk_score_boundaries(analysis, hits, severity):
    result = RiskScorer().score(analysis=analysis, signal_hits=hits)
    assert 0 <= result['risk_score'] <= 1
    assert result['severity'] == severity


def test_risk_scorer_tolerates_malformed_optional_hits():
    result = RiskScorer().score(analysis={}, signal_hits=[None, 'bad', {}])
    assert result['risk_score'] == 0


def test_full_ai_orchestration_works_lr_only_when_bert_absent():
    analysis = TelosXAIAnalysis()
    result = analysis.analyze_message(
        'We claim a DDoS attack and database leak against Europe',
        signal_hits=[{'id': 'rule', 'severity_hint': 'high'}],
    )
    assert set(result) == {'activity', 'attack_type', 'target_nation', 'meta'}
    assert result['meta']['bert_escalation_requested']
    assert not result['meta']['escalated_to_bert']
    assert 0 <= result['meta']['risk_score'] <= 1
