from ai.activity import ActivityPredictor
from ai.attack_type import AttackTypePredictor
from ai.target_nation import TargetNationPredictor


class TelosXAIAnalysis:
    def __init__(self):
        self.activity = ActivityPredictor()
        self.attack_type = AttackTypePredictor()
        self.target_nation = TargetNationPredictor()

    def analyze_message(self, text: str) -> dict:
        return {
            "activity": self.activity.predict(text),
            "attack_type": self.attack_type.predict(text),
            "target_nation": self.target_nation.predict(text),
        }