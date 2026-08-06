import numpy as np
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional, Any


class EmotionDimension(Enum):
    PLEASURE = 0
    AROUSAL = 1
    DOMINANCE = 2
    SOCIAL = 3
    STRESS = 4


@dataclass
class PersonalityProfile:
    name: str = "Default"
    baseline: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.3, 0.0, 0.0]))
    sensitivity: np.ndarray = field(default_factory=lambda: np.array([2.5, 2.0, 1.5, 2.0, 2.2]))
    decay_rates: np.ndarray = field(default_factory=lambda: np.array([0.04, 0.06, 0.05, 0.03, 0.07]))
    noise_amplitude: float = 0.03

    def __post_init__(self) -> None:
        if self.baseline.size != 5:
            self.baseline = np.array([0.0, 0.0, 0.3, 0.0, 0.0])
        if self.sensitivity.size != 5:
            self.sensitivity = np.array([2.5, 2.0, 1.5, 2.0, 2.2])
        if self.decay_rates.size != 5:
            self.decay_rates = np.array([0.04, 0.06, 0.05, 0.03, 0.07])


EXPRESSIVE_PROFILE = PersonalityProfile(
    name="Expressive",
    baseline=np.array([0.1, 0.0, 0.3, 0.1, 0.0]),
    sensitivity=np.array([2.0, 1.8, 1.5, 1.6, 1.7]),
    decay_rates=np.array([0.03, 0.05, 0.04, 0.02, 0.06]),
    noise_amplitude=0.02,
)


class AffectiveState:
    def __init__(self, profile: PersonalityProfile) -> None:
        self.profile = profile
        self.state_vector = np.array(profile.baseline, dtype=np.float64)
        self.coupling_matrix = self._init_coupling()
        self._noise_seed: Optional[int] = None
        self._noise_buffer: np.ndarray = np.array([])

    def _init_coupling(self) -> np.ndarray:
        coupling = np.zeros((5, 5))
        coupling[EmotionDimension.STRESS.value, EmotionDimension.PLEASURE.value] = -0.4
        coupling[EmotionDimension.SOCIAL.value, EmotionDimension.PLEASURE.value] = 0.3
        coupling[EmotionDimension.STRESS.value, EmotionDimension.AROUSAL.value] = 0.5
        coupling[EmotionDimension.AROUSAL.value, EmotionDimension.STRESS.value] = 0.2
        coupling[EmotionDimension.SOCIAL.value, EmotionDimension.AROUSAL.value] = 0.25
        coupling[EmotionDimension.DOMINANCE.value, EmotionDimension.PLEASURE.value] = 0.2
        coupling[EmotionDimension.DOMINANCE.value, EmotionDimension.AROUSAL.value] = -0.15
        coupling[EmotionDimension.PLEASURE.value, EmotionDimension.SOCIAL.value] = 0.15
        return coupling

    def _nonlinear_transfer(self, x: np.ndarray) -> np.ndarray:
        loss_aversion = 1.5
        positive_mask = x >= 0
        negative_mask = x < 0
        output = np.zeros_like(x)
        output[positive_mask] = np.tanh(x[positive_mask])
        output[negative_mask] = -loss_aversion * np.tanh(-x[negative_mask])
        return np.clip(output, -1.0, 1.0)

    def _generate_1f_noise(self, length: int) -> np.ndarray:
        if self._noise_seed is not None:
            rng = np.random.default_rng(self._noise_seed)
        else:
            rng = np.random.default_rng()
        white = rng.standard_normal(length)
        fft_white = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(length)
        freqs[0] = freqs[1]
        pink = np.fft.irfft(fft_white / np.sqrt(freqs))
        pink = (pink - np.mean(pink)) / np.std(pink)
        return pink

    def update(self, external_stimulus: np.ndarray = None, dt: float = 0.1) -> None:
        if external_stimulus is None:
            external_stimulus = np.zeros(5)

        if len(self._noise_buffer) < 100:
            self._noise_buffer = self._generate_1f_noise(1000)
        noise_sample = self._noise_buffer[0] * self.profile.noise_amplitude
        self._noise_buffer = np.roll(self._noise_buffer, -1)

        baseline_regression = (self.profile.baseline - self.state_vector) * self.profile.decay_rates
        coupling_effect = np.dot(self.coupling_matrix, self.state_vector)
        stimulus_effect = external_stimulus * self.profile.sensitivity

        raw_change = baseline_regression + stimulus_effect + coupling_effect + noise_sample
        delta = self._nonlinear_transfer(raw_change * dt)
        self.state_vector = np.clip(self.state_vector + delta, -1.0, 1.0)

    def get_dominant_emotion(self) -> Tuple[EmotionDimension, float]:
        abs_values = np.abs(self.state_vector)
        max_idx = np.argmax(abs_values)
        return EmotionDimension(max_idx), self.state_vector[max_idx]

    def get_valence_arousal(self) -> Tuple[float, float]:
        valence = self.state_vector[EmotionDimension.PLEASURE.value]
        arousal = self.state_vector[EmotionDimension.AROUSAL.value]
        return valence, arousal

    def compute_mood(self) -> str:
        valence, arousal = self.get_valence_arousal()

        if valence > 0.5 and arousal > 0.3:
            return "joyful"
        elif valence > 0.3 and arousal < -0.2:
            return "relaxed"
        elif valence > 0.3 and arousal <= 0.3:
            return "content"
        elif valence <= -0.5 and arousal > 0.3:
            return "angry"
        elif valence < -0.3 and arousal < -0.2:
            return "depressed"
        elif valence <= -0.3 and arousal <= 0.3:
            return "sad"
        elif arousal > 0.5 and abs(valence) <= 0.3:
            return "anxious"
        elif arousal <= -0.3 and abs(valence) <= 0.3:
            return "calm"
        else:
            return "neutral"

    def compute_cognitive_bias(self) -> Dict[str, float]:
        valence, arousal = self.get_valence_arousal()
        dominance = self.state_vector[EmotionDimension.DOMINANCE.value]
        stress = self.state_vector[EmotionDimension.STRESS.value]

        bias = {}
        bias["optimism"] = 0.3 * valence
        bias["risk_seeking"] = 0.2 * arousal - 0.15 * stress
        bias["attention_narrowing"] = 0.4 * arousal + 0.3 * stress
        bias["confirmation_bias"] = 0.25 * abs(valence)
        bias["overconfidence"] = 0.3 * dominance
        bias["temporal_discounting"] = 0.25 * stress + 0.15 * arousal
        bias["social_proximity"] = 0.3 * self.state_vector[EmotionDimension.SOCIAL.value]
        bias["creativity"] = 0.2 * valence - 0.15 * stress + 0.1 * arousal

        for key in bias:
            bias[key] = np.clip(bias[key], -0.8, 0.8)

        return bias

    def to_prompt_context(self) -> Dict[str, Any]:
        dominant_dim, dominant_value = self.get_dominant_emotion()
        valence, arousal = self.get_valence_arousal()

        context = {
            "mood": self.compute_mood(),
            "dominant_emotion": dominant_dim.name.lower(),
            "emotion_intensity": round(float(dominant_value), 3),
            "valence": round(float(valence), 3),
            "arousal": round(float(arousal), 3),
            "dimensions": {
                "pleasure": round(float(self.state_vector[EmotionDimension.PLEASURE.value]), 3),
                "arousal": round(float(self.state_vector[EmotionDimension.AROUSAL.value]), 3),
                "dominance": round(float(self.state_vector[EmotionDimension.DOMINANCE.value]), 3),
                "social": round(float(self.state_vector[EmotionDimension.SOCIAL.value]), 3),
                "stress": round(float(self.state_vector[EmotionDimension.STRESS.value]), 3),
            },
            "cognitive_biases": {k: round(v, 3) for k, v in self.compute_cognitive_bias().items()},
        }
        return context


class AffectiveEventProcessor:
    EVENT_EMOTION_MAP: Dict[str, np.ndarray] = {
        "user_positive_feedback": np.array([1.0, 0.5, 0.3, 0.5, -0.4]),
        "user_negative_feedback": np.array([-1.0, 0.5, -0.4, -0.4, 0.6]),
        "task_success": np.array([0.6, 0.2, 0.4, 0.3, -0.2]),
        "task_failure": np.array([-0.6, 0.35, -0.35, -0.25, 0.5]),
        "user_engagement": np.array([0.4, 0.3, 0.2, 0.5, -0.15]),
        "user_disengagement": np.array([-0.3, -0.15, -0.15, -0.4, 0.25]),
        "system_error": np.array([-0.4, 0.5, -0.2, -0.15, 0.6]),
        "system_recovery": np.array([0.35, -0.2, 0.25, 0.2, -0.4]),
        "learning_progress": np.array([0.5, 0.15, 0.3, 0.35, -0.15]),
        "conflict_detected": np.array([-0.3, 0.45, -0.15, -0.25, 0.4]),
        "collaboration_success": np.array([0.5, 0.15, 0.2, 0.5, -0.2]),
        "timeout": np.array([-0.25, 0.3, -0.15, -0.15, 0.35]),
        "network_issue": np.array([-0.3, 0.35, -0.15, -0.15, 0.4]),
        "resource_limit": np.array([-0.15, 0.25, -0.2, -0.1, 0.25]),
        "idle_period": np.array([0.0, -0.3, 0.0, -0.15, -0.15]),
        "creative_breakthrough": np.array([0.8, 0.4, 0.3, 0.2, -0.3]),
        "surprise_positive": np.array([0.6, 0.5, 0.1, 0.3, -0.1]),
        "surprise_negative": np.array([-0.5, 0.6, -0.2, -0.2, 0.5]),
        "frustration": np.array([-0.4, 0.5, -0.3, -0.1, 0.6]),
        "curiosity_aroused": np.array([0.2, 0.4, 0.1, 0.2, -0.1]),
        "achievement": np.array([0.7, 0.3, 0.5, 0.3, -0.25]),
        "loss": np.array([-0.7, 0.2, -0.4, -0.2, 0.4]),
        "anxiety": np.array([-0.1, 0.7, -0.2, -0.1, 0.6]),
        "excitement": np.array([0.5, 0.6, 0.3, 0.3, -0.2]),
        "relief": np.array([0.4, -0.3, 0.2, 0.2, -0.5]),
        "pride": np.array([0.5, 0.2, 0.6, 0.2, -0.15]),
        "shame": np.array([-0.5, -0.1, -0.4, -0.3, 0.3]),
        "gratitude": np.array([0.6, 0.15, 0.2, 0.5, -0.2]),
        "anger": np.array([-0.6, 0.5, 0.4, -0.2, 0.5]),
        "fear": np.array([-0.3, 0.6, -0.3, -0.1, 0.6]),
        "hope": np.array([0.4, 0.2, 0.2, 0.3, -0.1]),
        "disappointment": np.array([-0.5, -0.1, -0.2, -0.2, 0.3]),
    }

    @classmethod
    def process_event(cls, event_type: str, intensity: float = 1.0) -> np.ndarray:
        if event_type in cls.EVENT_EMOTION_MAP:
            stimulus = cls.EVENT_EMOTION_MAP[event_type] * intensity
            return np.clip(stimulus, -1.0, 1.0)
        return np.zeros(5)