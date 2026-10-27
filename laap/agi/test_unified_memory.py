"""
Test script for LAAP AGI Unified Memory System Interface
"""

import time
import sys
sys.path.insert(0, "<LOCAL_PATH_REDACTED>")

from laap.agi.unified_memory import UnifiedMemory
from laap.agi.memory_system import MemoryType, MemoryPriority


def test_init():
    print("\n=== Testing UnifiedMemory.__init__ ===")
    memory = UnifiedMemory()
    
    assert len(memory.working_memory) == 0
    assert memory.episodic_memory is not None
    assert memory.semantic_memory is not None
    assert memory.procedural_memory is not None
    assert memory.consolidator is not None
    assert "valence" in memory.emotional_state
    assert "arousal" in memory.emotional_state
    assert "dominance" in memory.emotional_state
    
    print("✓ UnifiedMemory initialization tests passed")


def test_working_memory():
    print("\n=== Testing Working Memory ===")
    memory = UnifiedMemory()
    
    for i in range(10):
        memory.add_to_working_memory(f"Item {i}")
    
    assert len(memory.working_memory) == 7
    
    contents = [item["content"] for item in memory.working_memory]
    assert "Item 0" not in contents
    assert "Item 9" in contents
    
    print("✓ Working Memory tests passed (capacity limit 7)")


def test_encode_experience():
    print("\n=== Testing encode_experience ===")
    memory = UnifiedMemory()
    
    result = memory.encode_experience(
        "I had a great meeting with the team to discuss project goals",
        emotional_valence=0.7,
        emotional_arousal=0.5,
        priority=MemoryPriority.IMPORTANT,
    )
    
    assert "episode_id" in result
    assert result["encoded_concepts"] > 0
    assert result["triggered_skills"] == 0
    
    result2 = memory.encode_experience(
        "I learned a new machine learning skill today",
        emotional_valence=0.8,
        emotional_arousal=0.6,
    )
    
    assert result2["triggered_skills"] == 1
    
    assert len(memory.episodic_memory.episodes) == 2
    assert len(memory.semantic_memory.concepts) > 0
    
    print("✓ encode_experience tests passed")


def test_encode_concept():
    print("\n=== Testing encode_concept ===")
    memory = UnifiedMemory()
    
    memory.encode_concept(
        "cat",
        "A small domesticated carnivorous mammal",
        category="animal",
        attributes={"furry": True, "meows": True},
    )
    
    memory.encode_concept(
        "dog",
        "A domesticated carnivorous mammal",
        category="animal",
        attributes={"barks": True, "loyal": True},
        related_concepts=["cat"],
    )
    
    assert "cat" in memory.semantic_memory.concepts
    assert "dog" in memory.semantic_memory.concepts
    
    concept = memory.semantic_memory.retrieve_concept("cat")
    assert concept is not None
    assert concept["category"] == "animal"
    
    assert len(memory.working_memory) == 2
    
    print("✓ encode_concept tests passed")


def test_encode_skill():
    print("\n=== Testing encode_skill ===")
    memory = UnifiedMemory()
    
    memory.encode_skill(
        "skill_python",
        "Python Programming",
        ["Understand requirements", "Write code", "Test code", "Debug"],
        context_triggers=["coding", "programming", "python"],
        domain="software",
        initial_proficiency=0.7,
    )
    
    assert "skill_python" in memory.procedural_memory.skills
    assert len(memory.working_memory) == 1
    
    skill = memory.procedural_memory.skills["skill_python"]
    assert skill["name"] == "Python Programming"
    assert skill["domain"] == "software"
    assert skill["proficiency"] == 0.7
    
    print("✓ encode_skill tests passed")


def test_query():
    print("\n=== Testing query ===")
    memory = UnifiedMemory()
    
    memory.encode_experience(
        "I had a meeting with the team to discuss project goals",
        emotional_valence=0.5,
        emotional_arousal=0.3,
    )
    
    memory.encode_concept(
        "meeting",
        "A gathering of people for discussion",
        category="event",
    )
    
    memory.encode_skill(
        "skill_meeting",
        "Conducting Effective Meetings",
        ["Prepare agenda", "Lead discussion", "Document decisions"],
        context_triggers=["meeting", "discussion"],
        domain="business",
    )
    
    results = memory.query("meeting")
    
    assert len(results) >= 1
    assert all("type" in r for r in results)
    
    episodic_results = [r for r in results if r["type"] == "episodic"]
    semantic_results = [r for r in results if r["type"] == "semantic"]
    procedural_results = [r for r in results if r["type"] == "procedural"]
    
    assert len(episodic_results) >= 1
    assert len(semantic_results) >= 1
    assert len(procedural_results) >= 1
    
    results_episodic_only = memory.query("meeting", include_types=[MemoryType.EPISODIC])
    assert all(r["type"] == "episodic" for r in results_episodic_only)
    
    print("✓ query tests passed")


def test_rank_results():
    print("\n=== Testing _rank_results ===")
    memory = UnifiedMemory()
    
    memory.encode_experience("I learned Python programming today", emotional_valence=0.8, emotional_arousal=0.6)
    memory.encode_experience("I drank coffee this morning", emotional_valence=0.2, emotional_arousal=0.1)
    
    results = memory.query("programming")
    
    assert len(results) >= 1
    assert results[0]["type"] == "episodic"
    assert "programming" in results[0]["content"].lower()
    
    print("✓ _rank_results tests passed")


def test_retrieve_context():
    print("\n=== Testing retrieve_context ===")
    memory = UnifiedMemory()
    
    memory.encode_experience(
        "I solved a difficult coding problem with great satisfaction",
        emotional_valence=0.8,
        emotional_arousal=0.7,
    )
    
    memory.encode_concept("coding", "The process of writing computer programs", category="skill")
    
    memory.encode_skill(
        "skill_debugging",
        "Debugging Code",
        ["Identify bug", "Reproduce issue", "Fix bug", "Test fix"],
        context_triggers=["coding", "debugging", "problem"],
    )
    
    context = memory.retrieve_context(
        "I need to solve a coding problem",
        emotional_valence=0.5,
        emotional_arousal=0.5,
    )
    
    assert len(context) >= 1
    
    types_found = set(r["type"] for r in context)
    assert "episodic" in types_found or "semantic" in types_found or "procedural" in types_found
    
    print("✓ retrieve_context tests passed")


def test_generate_memory_prompt():
    print("\n=== Testing generate_memory_prompt ===")
    memory = UnifiedMemory()
    
    memory.encode_experience("I had a productive coding session yesterday")
    memory.encode_concept("productivity", "The state of being productive", category="concept")
    memory.encode_skill(
        "skill_coding",
        "Coding",
        ["Write code", "Test", "Refactor"],
        context_triggers=["coding"],
    )
    
    prompt = memory.generate_memory_prompt("coding")
    
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    
    assert "Relevant Experiences" in prompt or "Relevant Concepts" in prompt or "Relevant Skills" in prompt
    
    print("✓ generate_memory_prompt tests passed")


def test_get_recent_episodes():
    print("\n=== Testing get_recent_episodes ===")
    memory = UnifiedMemory()
    
    for i in range(5):
        memory.encode_experience(f"Experience {i}")
        time.sleep(0.01)
    
    recent = memory.get_recent_episodes(hours=1.0)
    
    assert len(recent) == 5
    assert recent[0]["content"] == "Experience 4"
    
    recent_limited = memory.get_recent_episodes(max_results=2)
    assert len(recent_limited) == 2
    
    print("✓ get_recent_episodes tests passed")


def test_get_related_concepts():
    print("\n=== Testing get_related_concepts ===")
    memory = UnifiedMemory()
    
    memory.encode_concept("cat", "A small animal", category="animal")
    memory.encode_concept("dog", "A medium animal", category="animal")
    memory.encode_concept("animal", "A living creature", category="biology")
    
    memory.semantic_memory.encode_fact("cat", "is_a", "animal")
    memory.semantic_memory.encode_fact("dog", "is_a", "animal")
    
    related = memory.get_related_concepts("cat", max_results=3)
    
    assert len(related) >= 1
    
    related_ids = [r["id"] for r in related]
    assert "animal" in related_ids or "dog" in related_ids
    
    print("✓ get_related_concepts tests passed")


def test_get_relevant_skills():
    print("\n=== Testing get_relevant_skills ===")
    memory = UnifiedMemory()
    
    memory.encode_skill(
        "skill_data_analysis",
        "Data Analysis",
        ["Collect data", "Clean data", "Analyze data", "Visualize results"],
        context_triggers=["data", "analysis", "statistics"],
        domain="data_science",
        initial_proficiency=0.8,
    )
    
    memory.encode_skill(
        "skill_reporting",
        "Reporting",
        ["Compile findings", "Create report", "Present results"],
        context_triggers=["report", "presentation"],
        domain="business",
    )
    
    skills = memory.get_relevant_skills("I need to analyze some data")
    
    assert len(skills) >= 1
    assert skills[0]["id"] == "Data Analysis"
    assert skills[0]["domain"] == "data_science"
    
    print("✓ get_relevant_skills tests passed")


def test_consolidate():
    print("\n=== Testing consolidate ===")
    memory = UnifiedMemory()
    
    memory.encode_experience("I learned how to bake bread today", emotional_valence=0.7, emotional_arousal=0.6)
    memory.encode_experience("I always drink tea in the afternoon", emotional_valence=0.3, emotional_arousal=0.2)
    
    result = memory.consolidate()
    
    assert result["consolidation_count"] == 1
    assert result["was_consolidated"] is True
    
    result2 = memory.consolidate()
    assert result2["was_consolidated"] is False
    
    print("✓ consolidate tests passed")


def test_get_dream_report():
    print("\n=== Testing get_dream_report ===")
    memory = UnifiedMemory()
    
    memory.encode_experience("Dream test 1", emotional_valence=0.5, emotional_arousal=0.5)
    memory.encode_experience("Dream test 2", emotional_valence=0.6, emotional_arousal=0.6)
    
    memory.consolidate()
    
    dreams = memory.get_dream_report()
    
    assert len(dreams) >= 1
    assert "Dream:" in dreams[0]
    
    print("✓ get_dream_report tests passed")


def test_get_memory_summary():
    print("\n=== Testing get_memory_summary ===")
    memory = UnifiedMemory()
    
    memory.encode_experience("Test experience")
    memory.encode_concept("test_concept", "A test concept")
    memory.encode_skill("test_skill", "Test Skill", ["Step 1"])
    memory.consolidate()
    
    summary = memory.get_memory_summary()
    
    assert summary["episodic_memory_count"] == 1
    assert summary["semantic_memory_count"] >= 1
    assert summary["procedural_memory_count"] >= 1
    assert summary["consolidation_count"] == 1
    assert "emotional_state" in summary
    
    print("✓ get_memory_summary tests passed")


def test_integration():
    print("\n=== Testing Full Integration ===")
    memory = UnifiedMemory()
    
    for i in range(8):
        memory.encode_experience(
            f"Working on AGI development task {i}",
            emotional_valence=0.5 + i * 0.1,
            emotional_arousal=0.3 + i * 0.1,
        )
    
    memory.encode_concept("agi", "Artificial General Intelligence", category="technology")
    memory.encode_concept("development", "The process of creating software", category="process")
    
    memory.encode_skill(
        "skill_agi_dev",
        "AGI Development",
        ["Design architecture", "Implement modules", "Test integration", "Optimize performance"],
        context_triggers=["agi", "development", "coding"],
        domain="ai",
        initial_proficiency=0.6,
    )
    
    memory.consolidate()
    
    results = memory.query("agi development")
    assert len(results) >= 1
    
    context = memory.retrieve_context("working on agi", emotional_valence=0.7, emotional_arousal=0.5)
    assert len(context) >= 1
    
    prompt = memory.generate_memory_prompt("agi development")
    assert len(prompt) > 0
    
    summary = memory.get_memory_summary()
    assert summary["episodic_memory_count"] == 8
    assert summary["semantic_memory_count"] > 0
    assert summary["procedural_memory_count"] > 0
    assert summary["consolidation_count"] == 1
    
    print("✓ Full Integration tests passed")


if __name__ == "__main__":
    print("Running LAAP AGI Unified Memory System Tests...")
    
    test_init()
    test_working_memory()
    test_encode_experience()
    test_encode_concept()
    test_encode_skill()
    test_query()
    test_rank_results()
    test_retrieve_context()
    test_generate_memory_prompt()
    test_get_recent_episodes()
    test_get_related_concepts()
    test_get_relevant_skills()
    test_consolidate()
    test_get_dream_report()
    test_get_memory_summary()
    test_integration()
    
    print("\n=== All tests passed! ===")