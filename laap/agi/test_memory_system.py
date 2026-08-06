"""
Test script for LAAP AGI Memory System
"""

import time
import sys
sys.path.insert(0, "<LOCAL_PATH_REDACTED>")

from laap.agi.memory_system import (
    MemoryType,
    MemoryPriority,
    MemoryTrace,
    EpisodicMemory,
    SemanticMemory,
    ProceduralMemory,
    MemoryConsolidator,
)


def test_memory_type_enum():
    print("\n=== Testing MemoryType Enum ===")
    assert MemoryType.EPISODIC.value == "episodic"
    assert MemoryType.SEMANTIC.value == "semantic"
    assert MemoryType.PROCEDURAL.value == "procedural"
    print("✓ MemoryType enum tests passed")


def test_memory_priority_enum():
    print("\n=== Testing MemoryPriority Enum ===")
    assert MemoryPriority.CORE.value == 5
    assert MemoryPriority.IMPORTANT.value == 4
    assert MemoryPriority.RELEVANT.value == 3
    assert MemoryPriority.INCIDENTAL.value == 2
    assert MemoryPriority.FLEETING.value == 1
    print("✓ MemoryPriority enum tests passed")


def test_memory_trace():
    print("\n=== Testing MemoryTrace ===")
    trace = MemoryTrace(
        trace_id="test_001",
        memory_type=MemoryType.EPISODIC,
        content="Test content",
        emotional_valence=0.8,
        emotional_arousal=0.6,
    )

    assert trace.strength > 0.5
    initial_rehearsal = trace.rehearsal_count

    trace.access()
    assert trace.rehearsal_count == initial_rehearsal + 1

    initial_confidence = trace.confidence
    trace.decay(100)
    assert trace.confidence < initial_confidence
    print("✓ MemoryTrace tests passed")


def test_episodic_memory():
    print("\n=== Testing EpisodicMemory ===")
    episodic = EpisodicMemory(capacity=10)

    trace1 = episodic.encode_episode(
        "I had a meeting with the team to discuss project goals",
        emotional_valence=0.5,
        emotional_arousal=0.3,
        priority=MemoryPriority.IMPORTANT,
    )
    assert trace1 is not None

    trace2 = episodic.encode_episode(
        "I learned a new programming technique today",
        emotional_valence=0.7,
        emotional_arousal=0.5,
    )

    similar = episodic.retrieve_similar("meeting")
    assert len(similar) >= 1

    recent = episodic.retrieve_by_time(time.time() - 100, time.time())
    assert len(recent) >= 2

    emotional = episodic.retrieve_by_emotion(0.5, 0.3)
    assert len(emotional) >= 1

    narrative = episodic.get_life_narrative()
    assert isinstance(narrative, str)

    print("✓ EpisodicMemory tests passed")


def test_semantic_memory():
    print("\n=== Testing SemanticMemory ===")
    semantic = SemanticMemory()

    semantic.encode_concept(
        "cat",
        "A small domesticated carnivorous mammal",
        category="animal",
        attributes={"furry": True, "meows": True},
    )

    semantic.encode_concept(
        "dog",
        "A domesticated carnivorous mammal",
        category="animal",
        attributes={"barks": True, "loyal": True},
    )

    semantic.encode_fact("cat", "is_a", "animal", confidence=0.9)
    semantic.encode_fact("dog", "is_a", "animal", confidence=0.9)
    semantic.encode_fact("cat", "lives_with", "human", confidence=0.8)

    concept = semantic.retrieve_concept("cat")
    assert concept is not None
    assert concept["definition"] == "A small domesticated carnivorous mammal"

    relation = semantic.infer_relation("cat", "dog")
    assert relation is not None
    assert len(relation) > 0

    activated = semantic.spread_activation(["cat"])
    assert len(activated) >= 1

    results = semantic.query(["mammal"])
    assert len(results) >= 1

    print("✓ SemanticMemory tests passed")


def test_procedural_memory():
    print("\n=== Testing ProceduralMemory ===")
    procedural = ProceduralMemory()

    procedural.encode_skill(
        "skill_coding",
        "Python Programming",
        ["Understand requirements", "Write code", "Test code", "Debug"],
        context_triggers=["coding", "programming", "python"],
        domain="software",
        initial_proficiency=0.6,
    )

    procedural.encode_habit(
        "habit_morning",
        "morning coffee",
        "Drink coffee and plan the day",
        initial_strength=0.5,
    )

    proficiency = procedural.practice_skill("skill_coding", success=True)
    assert proficiency > 0.6

    skills = procedural.retrieve_skill("I need to do some programming")
    assert len(skills) >= 1

    strength = procedural.reinforce_habit("habit_morning", reward=1.0)
    assert strength > 0.5

    strength = procedural.reinforce_habit("habit_morning", reward=1.0)
    assert strength > 0.55

    response = procedural.check_automated_response("time for morning coffee")
    assert response is None

    for _ in range(5):
        procedural.reinforce_habit("habit_morning", reward=1.0)

    response = procedural.check_automated_response("time for morning coffee")
    assert response == "Drink coffee and plan the day"

    print("✓ ProceduralMemory tests passed")


def test_memory_consolidator():
    print("\n=== Testing MemoryConsolidator ===")
    episodic = EpisodicMemory()
    semantic = SemanticMemory()
    procedural = ProceduralMemory()

    consolidator = MemoryConsolidator(episodic, semantic, procedural)

    trace1 = episodic.encode_episode(
        "I learned how to bake bread today",
        emotional_valence=0.7,
        emotional_arousal=0.6,
    )
    trace2 = episodic.encode_episode(
        "I always drink tea in the afternoon",
        emotional_valence=0.3,
        emotional_arousal=0.2,
    )

    consolidator.queue_for_consolidation(trace1.trace_id)
    consolidator.queue_for_consolidation(trace2.trace_id)

    consolidator.consolidate()

    assert consolidator.consolidation_count == 1

    dreams = consolidator.get_dream_report()
    assert len(dreams) >= 1

    assert "bake" in semantic.concepts or "bread" in semantic.concepts

    print("✓ MemoryConsolidator tests passed")


def test_integration():
    print("\n=== Testing Integration ===")
    episodic = EpisodicMemory()
    semantic = SemanticMemory()
    procedural = ProceduralMemory()
    consolidator = MemoryConsolidator(episodic, semantic, procedural)

    for i in range(5):
        trace = episodic.encode_episode(
            f"Event {i}: Working on AGI development",
            emotional_valence=0.5 + i * 0.1,
            emotional_arousal=0.3 + i * 0.1,
        )
        consolidator.queue_for_consolidation(trace.trace_id)

    consolidator.consolidate()

    assert len(episodic.episodes) == 5
    assert consolidator.consolidation_count == 1
    assert len(semantic.concepts) > 0

    print("✓ Integration tests passed")


if __name__ == "__main__":
    print("Running LAAP AGI Memory System Tests...")

    test_memory_type_enum()
    test_memory_priority_enum()
    test_memory_trace()
    test_episodic_memory()
    test_semantic_memory()
    test_procedural_memory()
    test_memory_consolidator()
    test_integration()

    print("\n=== All tests passed! ===")
