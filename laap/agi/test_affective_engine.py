import numpy as np
from affective_engine import (
    EmotionDimension,
    PersonalityProfile,
    AffectiveState,
    AffectiveEventProcessor,
)


def test_emotion_dimension():
    print("=== Testing EmotionDimension ===")
    assert EmotionDimension.PLEASURE.value == 0
    assert EmotionDimension.AROUSAL.value == 1
    assert EmotionDimension.DOMINANCE.value == 2
    assert EmotionDimension.SOCIAL.value == 3
    assert EmotionDimension.STRESS.value == 4
    print("✓ EmotionDimension test passed")


def test_personality_profile():
    print("\n=== Testing PersonalityProfile ===")
    profile = PersonalityProfile(name="TestProfile")
    assert profile.name == "TestProfile"
    assert profile.baseline.shape == (5,)
    assert profile.sensitivity.shape == (5,)
    assert profile.decay_rates.shape == (5,)
    assert profile.noise_amplitude == 0.05

    custom_baseline = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    custom_profile = PersonalityProfile(baseline=custom_baseline)
    np.testing.assert_array_equal(custom_profile.baseline, custom_baseline)

    invalid_profile = PersonalityProfile(baseline=np.array([1.0]))
    assert invalid_profile.baseline.shape == (5,)
    print("✓ PersonalityProfile test passed")


def test_affective_state_init():
    print("\n=== Testing AffectiveState Initialization ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)
    assert state.state_vector.shape == (5,)
    assert state.coupling_matrix.shape == (5, 5)
    np.testing.assert_array_equal(state.state_vector, profile.baseline)
    print("✓ AffectiveState initialization test passed")


def test_coupling_matrix():
    print("\n=== Testing Coupling Matrix ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)
    coupling = state.coupling_matrix

    assert coupling[EmotionDimension.STRESS.value, EmotionDimension.PLEASURE.value] == -0.4
    assert coupling[EmotionDimension.SOCIAL.value, EmotionDimension.PLEASURE.value] == 0.3
    assert coupling[EmotionDimension.STRESS.value, EmotionDimension.AROUSAL.value] == 0.5
    print("✓ Coupling matrix test passed")


def test_nonlinear_transfer():
    print("\n=== Testing Nonlinear Transfer ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)

    test_input = np.array([0.5, -0.5, 0.0, 1.0, -1.0])
    output = state._nonlinear_transfer(test_input)

    assert output[0] > 0
    assert output[1] < 0
    assert output[2] == 0
    assert abs(output[1]) > abs(output[0])
    assert np.all(output >= -1) and np.all(output <= 1)
    print("✓ Nonlinear transfer test passed")


def test_noise_generation():
    print("\n=== Testing 1/f Noise Generation ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)

    noise = state._generate_1f_noise(1000)
    assert noise.shape == (1000,)
    assert np.abs(np.mean(noise)) < 0.1
    assert np.abs(np.std(noise) - 1.0) < 0.1
    print("✓ 1/f noise generation test passed")


def test_update():
    print("\n=== Testing AffectiveState Update ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)

    initial_state = state.state_vector.copy()
    stimulus = np.array([0.5, 0.0, 0.0, 0.0, 0.0])

    state.update(external_stimulus=stimulus, dt=0.1)
    assert not np.array_equal(state.state_vector, initial_state)
    assert np.all(state.state_vector >= -1) and np.all(state.state_vector <= 1)

    for _ in range(100):
        state.update(dt=0.1)

    assert np.all(state.state_vector >= -1) and np.all(state.state_vector <= 1)
    print("✓ AffectiveState update test passed")


def test_dominant_emotion():
    print("\n=== Testing Dominant Emotion ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)

    state.state_vector = np.array([0.8, 0.2, 0.1, 0.3, 0.4])
    dim, value = state.get_dominant_emotion()
    assert dim == EmotionDimension.PLEASURE
    assert value == 0.8

    state.state_vector = np.array([0.1, 0.9, 0.2, 0.3, 0.1])
    dim, value = state.get_dominant_emotion()
    assert dim == EmotionDimension.AROUSAL
    assert value == 0.9
    print("✓ Dominant emotion test passed")


def test_valence_arousal():
    print("\n=== Testing Valence-Arousal ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)

    state.state_vector = np.array([0.6, 0.4, 0.2, 0.3, 0.1])
    valence, arousal = state.get_valence_arousal()
    assert valence == 0.6
    assert arousal == 0.4
    print("✓ Valence-arousal test passed")


def test_mood_computation():
    print("\n=== Testing Mood Computation ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)

    state.state_vector = np.array([0.6, 0.4, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "joyful"

    state.state_vector = np.array([0.4, 0.2, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "content"

    state.state_vector = np.array([-0.6, 0.4, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "angry"

    state.state_vector = np.array([-0.4, 0.2, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "sad"

    state.state_vector = np.array([0.0, 0.6, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "anxious"

    state.state_vector = np.array([0.0, -0.4, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "calm"

    state.state_vector = np.array([0.4, -0.3, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "relaxed"

    state.state_vector = np.array([-0.4, -0.3, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "depressed"

    state.state_vector = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
    assert state.compute_mood() == "neutral"
    print("✓ Mood computation test passed")


def test_cognitive_bias():
    print("\n=== Testing Cognitive Bias ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)

    biases = state.compute_cognitive_bias()
    assert "optimism" in biases
    assert "risk_seeking" in biases
    assert "attention_narrowing" in biases
    assert "confirmation_bias" in biases
    assert "overconfidence" in biases
    assert "temporal_discounting" in biases
    assert "social_proximity" in biases
    assert "creativity" in biases

    for value in biases.values():
        assert -0.8 <= value <= 0.8
    print("✓ Cognitive bias test passed")


def test_prompt_context():
    print("\n=== Testing Prompt Context ===")
    profile = PersonalityProfile()
    state = AffectiveState(profile)

    context = state.to_prompt_context()
    assert "mood" in context
    assert "dominant_emotion" in context
    assert "emotion_intensity" in context
    assert "valence" in context
    assert "arousal" in context
    assert "dimensions" in context
    assert "cognitive_biases" in context

    assert isinstance(context["mood"], str)
    assert isinstance(context["dominant_emotion"], str)
    assert isinstance(context["emotion_intensity"], float)
    assert isinstance(context["valence"], float)
    assert isinstance(context["arousal"], float)
    print("✓ Prompt context test passed")


def test_event_processor():
    print("\n=== Testing AffectiveEventProcessor ===")
    stimulus = AffectiveEventProcessor.process_event("user_positive_feedback")
    assert stimulus.shape == (5,)
    assert stimulus[EmotionDimension.PLEASURE.value] > 0
    assert stimulus[EmotionDimension.STRESS.value] < 0

    stimulus = AffectiveEventProcessor.process_event("user_negative_feedback")
    assert stimulus[EmotionDimension.PLEASURE.value] < 0
    assert stimulus[EmotionDimension.STRESS.value] > 0

    stimulus = AffectiveEventProcessor.process_event("unknown_event")
    np.testing.assert_array_equal(stimulus, np.zeros(5))

    stimulus = AffectiveEventProcessor.process_event("task_success", intensity=0.5)
    assert stimulus[EmotionDimension.PLEASURE.value] == 0.2
    print("✓ AffectiveEventProcessor test passed")


def test_integration():
    print("\n=== Testing Integration ===")
    profile = PersonalityProfile(name="TestAgent")
    state = AffectiveState(profile)

    events = ["user_positive_feedback", "task_success", "user_negative_feedback"]
    for event in events:
        stimulus = AffectiveEventProcessor.process_event(event)
        state.update(external_stimulus=stimulus, dt=0.5)

    context = state.to_prompt_context()
    assert context["mood"] in ["joyful", "content", "neutral", "sad", "angry"]
    print("✓ Integration test passed")


def main():
    print("Running affective_engine tests...\n")
    test_emotion_dimension()
    test_personality_profile()
    test_affective_state_init()
    test_coupling_matrix()
    test_nonlinear_transfer()
    test_noise_generation()
    test_update()
    test_dominant_emotion()
    test_valence_arousal()
    test_mood_computation()
    test_cognitive_bias()
    test_prompt_context()
    test_event_processor()
    test_integration()
    print("\n=== All tests passed! ===")


if __name__ == "__main__":
    main()