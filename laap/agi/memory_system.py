"""
LAAP AGI — Hierarchical Memory System

Implements a comprehensive multi-layer memory architecture:
- Episodic Memory: Event sequences with emotional tagging
- Semantic Memory: Concept networks with relational reasoning
- Procedural Memory: Skills, habits, and automated responses

Features:
- MemoryTrace with strength calculation and decay
- Emotional valence/arousal tagging
- Temporal clustering for episodic memory
- Concept network with BFS-based relation inference
- Spread activation for semantic retrieval
- Rescorla-Wagner style habit reinforcement
- Memory consolidation with dream generation
"""

from __future__ import annotations

import time
import uuid
import math
import heapq
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from collections import defaultdict, deque


class MemoryType(Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class MemoryPriority(Enum):
    CORE = 5
    IMPORTANT = 4
    RELEVANT = 3
    INCIDENTAL = 2
    FLEETING = 1


@dataclass
class MemoryTrace:
    trace_id: str
    memory_type: MemoryType
    content: str
    timestamp: float = field(default_factory=time.time)
    emotional_valence: float = 0.0
    emotional_arousal: float = 0.0
    rehearsal_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    associations: List[str] = field(default_factory=list)
    source_episode: Optional[str] = None
    confidence: float = 0.5
    decay_rate: float = 0.01

    @property
    def strength(self) -> float:
        age = time.time() - self.timestamp
        decay_factor = math.exp(-self.decay_rate * age)
        rehearsal_factor = 1 + 0.1 * self.rehearsal_count
        emotional_factor = 1 + (abs(self.emotional_valence) + self.emotional_arousal) * 0.5
        confidence_factor = self.confidence
        return min(1.0, decay_factor * rehearsal_factor * emotional_factor * confidence_factor)

    def access(self) -> None:
        self.last_accessed = time.time()
        self.rehearsal_count += 1

    def decay(self, time_passed: float = 1.0) -> None:
        decay_factor = math.exp(-self.decay_rate * time_passed)
        self.confidence = max(0.01, self.confidence * decay_factor)


class EpisodicMemory:
    def __init__(self, capacity: int = 1000):
        self.capacity = capacity
        self.episodes: List[MemoryTrace] = []
        self._time_index: Dict[float, List[str]] = defaultdict(list)
        self._emotion_index: Dict[Tuple[int, int], List[str]] = defaultdict(list)
        self._narrative_cache: Dict[str, str] = {}

    def _emotion_key(self, valence: float, arousal: float) -> Tuple[int, int]:
        valence_bin = int(valence * 10)
        arousal_bin = int(arousal * 10)
        return (valence_bin, arousal_bin)

    def encode_episode(
        self,
        content: str,
        emotional_valence: float = 0.0,
        emotional_arousal: float = 0.0,
        associations: Optional[List[str]] = None,
        priority: MemoryPriority = MemoryPriority.RELEVANT,
    ) -> MemoryTrace:
        trace_id = f"ep_{uuid.uuid4().hex[:8]}"
        trace = MemoryTrace(
            trace_id=trace_id,
            memory_type=MemoryType.EPISODIC,
            content=content,
            emotional_valence=emotional_valence,
            emotional_arousal=emotional_arousal,
            associations=associations or [],
            confidence=priority.value / 5.0,
            decay_rate=0.001 / priority.value,
        )

        if len(self.episodes) >= self.capacity:
            weakest_idx = min(range(len(self.episodes)), key=lambda i: self.episodes[i].strength)
            old_trace = self.episodes.pop(weakest_idx)
            self._cleanup_index(old_trace)

        self.episodes.append(trace)
        self._time_index[trace.timestamp].append(trace_id)
        emotion_key = self._emotion_key(emotional_valence, emotional_arousal)
        self._emotion_index[emotion_key].append(trace_id)

        return trace

    def _cleanup_index(self, trace: MemoryTrace) -> None:
        if trace.timestamp in self._time_index:
            self._time_index[trace.timestamp].remove(trace.trace_id)
            if not self._time_index[trace.timestamp]:
                del self._time_index[trace.timestamp]
        emotion_key = self._emotion_key(trace.emotional_valence, trace.emotional_arousal)
        if emotion_key in self._emotion_index:
            self._emotion_index[emotion_key].remove(trace.trace_id)
            if not self._emotion_index[emotion_key]:
                del self._emotion_index[emotion_key]

    def _generate_narrative(self, traces: List[MemoryTrace]) -> str:
        if not traces:
            return ""
        sorted_traces = sorted(traces, key=lambda t: t.timestamp)
        events = [t.content for t in sorted_traces]
        return " → ".join(events)

    def retrieve_similar(
        self,
        query_content: str,
        max_results: int = 5,
        emotion_threshold: float = 0.3,
    ) -> List[MemoryTrace]:
        query_words = set(query_content.lower().split())
        candidates = []

        for trace in self.episodes:
            trace_words = set(trace.content.lower().split())
            similarity = len(query_words & trace_words) / max(len(query_words), len(trace_words))
            if similarity > 0:
                candidates.append((similarity, trace))

        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates[:max_results]]

    def retrieve_by_time(
        self,
        start_time: float,
        end_time: float,
        max_results: int = 10,
    ) -> List[MemoryTrace]:
        candidates = []
        for timestamp, trace_ids in self._time_index.items():
            if start_time <= timestamp <= end_time:
                for trace_id in trace_ids:
                    trace = next((t for t in self.episodes if t.trace_id == trace_id), None)
                    if trace:
                        candidates.append(trace)
        candidates.sort(key=lambda t: t.timestamp)
        return candidates[:max_results]

    def retrieve_by_emotion(
        self,
        target_valence: float,
        target_arousal: float,
        tolerance: float = 0.2,
        max_results: int = 10,
    ) -> List[MemoryTrace]:
        target_key = self._emotion_key(target_valence, target_arousal)
        candidates = []

        for (valence_bin, arousal_bin), trace_ids in self._emotion_index.items():
            actual_valence = valence_bin / 10.0
            actual_arousal = arousal_bin / 10.0
            distance = math.sqrt(
                (actual_valence - target_valence) ** 2 +
                (actual_arousal - target_arousal) ** 2
            )
            if distance <= tolerance:
                for trace_id in trace_ids:
                    trace = next((t for t in self.episodes if t.trace_id == trace_id), None)
                    if trace:
                        candidates.append((distance, trace))

        candidates.sort(key=lambda x: x[0])
        return [c[1] for c in candidates[:max_results]]

    def get_life_narrative(self, recent_hours: float = 24.0) -> str:
        cutoff_time = time.time() - recent_hours * 3600
        recent_episodes = [
            t for t in self.episodes
            if t.timestamp >= cutoff_time
            and t.emotional_arousal > 0.2
        ]
        return self._generate_narrative(recent_episodes)


class SemanticMemory:
    def __init__(self):
        self.concepts: Dict[str, Dict[str, Any]] = {}
        self.relations: Dict[str, List[Tuple[str, str, float]]] = defaultdict(list)
        self.hierarchy: Dict[str, List[str]] = defaultdict(list)

    def encode_concept(
        self,
        concept_id: str,
        definition: str,
        category: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.concepts[concept_id] = {
            "definition": definition,
            "category": category,
            "attributes": attributes or {},
            "created_at": time.time(),
            "access_count": 0,
        }

        if category:
            self.hierarchy[category].append(concept_id)

    def _add_relation(
        self,
        concept_a: str,
        concept_b: str,
        relation_type: str,
        weight: float = 1.0,
    ) -> None:
        if concept_a not in self.concepts or concept_b not in self.concepts:
            return
        self.relations[concept_a].append((concept_b, relation_type, weight))
        self.relations[concept_b].append((concept_a, relation_type, weight))

    def encode_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 0.8,
    ) -> None:
        if subject not in self.concepts:
            self.encode_concept(subject, f"Concept related to {obj}")
        if obj not in self.concepts:
            self.encode_concept(obj, f"Concept related to {subject}")

        self._add_relation(subject, obj, predicate, confidence)

    def retrieve_concept(self, concept_id: str) -> Optional[Dict[str, Any]]:
        concept = self.concepts.get(concept_id)
        if concept:
            concept["access_count"] = concept.get("access_count", 0) + 1
        return concept

    def infer_relation(
        self,
        concept_a: str,
        concept_b: str,
        max_depth: int = 3,
    ) -> Optional[List[Tuple[str, str, float]]]:
        if concept_a not in self.concepts or concept_b not in self.concepts:
            return None

        queue = deque([(concept_a, [])])
        visited = {concept_a}

        while queue:
            current, path = queue.popleft()

            if current == concept_b:
                return path

            if len(path) >= max_depth:
                continue

            for neighbor, relation_type, weight in self.relations.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = path + [(current, relation_type, neighbor)]
                    queue.append((neighbor, new_path))

        return None

    def spread_activation(
        self,
        seed_concepts: List[str],
        activation_threshold: float = 0.1,
        max_concepts: int = 10,
        decay: float = 0.5,
    ) -> List[Tuple[str, float]]:
        activation: Dict[str, float] = {}
        for concept in seed_concepts:
            if concept in self.concepts:
                activation[concept] = 1.0

        for _ in range(3):
            new_activation = activation.copy()
            for concept, act_level in activation.items():
                if act_level < activation_threshold:
                    continue
                for neighbor, _, weight in self.relations.get(concept, []):
                    new_activation[neighbor] = max(
                        new_activation.get(neighbor, 0),
                        act_level * decay * weight,
                    )
            activation = new_activation

        results = [(c, a) for c, a in activation.items() if a >= activation_threshold]
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_concepts]

    def query(self, keywords: List[str], max_results: int = 10) -> List[Tuple[str, float]]:
        matching_concepts = []
        for concept_id, concept_data in self.concepts.items():
            text = f"{concept_id} {concept_data['definition']}"
            score = sum(1 for kw in keywords if kw.lower() in text.lower())
            if score > 0:
                matching_concepts.append((concept_id, score))

        matching_concepts.sort(key=lambda x: x[1], reverse=True)
        seed_concepts = [c[0] for c in matching_concepts[:5]]

        if seed_concepts:
            activated = self.spread_activation(seed_concepts)
            return activated[:max_results]

        return matching_concepts[:max_results]


class ProceduralMemory:
    def __init__(self):
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.habits: Dict[str, Dict[str, Any]] = {}
        self.automated_responses: Dict[str, str] = {}

    def encode_skill(
        self,
        skill_id: str,
        name: str,
        steps: List[str],
        context_triggers: Optional[List[str]] = None,
        domain: str = "",
        initial_proficiency: float = 0.5,
    ) -> None:
        self.skills[skill_id] = {
            "name": name,
            "steps": steps,
            "context_triggers": context_triggers or [],
            "domain": domain,
            "proficiency": initial_proficiency,
            "practice_count": 0,
            "success_count": 0,
            "last_practiced": time.time(),
        }

    def practice_skill(self, skill_id: str, success: bool = True) -> float:
        skill = self.skills.get(skill_id)
        if not skill:
            return 0.0

        skill["practice_count"] += 1
        if success:
            skill["success_count"] += 1
        skill["last_practiced"] = time.time()

        skill["proficiency"] = min(
            1.0,
            skill["success_count"] / max(skill["practice_count"], 1),
        )
        return skill["proficiency"]

    def retrieve_skill(self, context: str, max_results: int = 3) -> List[Dict[str, Any]]:
        context_lower = context.lower()
        matches = []

        for skill_id, skill in self.skills.items():
            for trigger in skill["context_triggers"]:
                if trigger.lower() in context_lower:
                    matches.append((skill_id, skill))
                    break

        matches.sort(key=lambda x: x[1]["proficiency"], reverse=True)
        return [m[1] for m in matches[:max_results]]

    def encode_habit(
        self,
        habit_id: str,
        stimulus: str,
        response: str,
        initial_strength: float = 0.5,
    ) -> None:
        self.habits[habit_id] = {
            "stimulus": stimulus,
            "response": response,
            "strength": initial_strength,
            "trials": 0,
            "successes": 0,
        }

    def reinforce_habit(
        self,
        habit_id: str,
        reward: float = 1.0,
        learning_rate: float = 0.1,
    ) -> float:
        habit = self.habits.get(habit_id)
        if not habit:
            return 0.0

        habit["trials"] += 1
        if reward > 0:
            habit["successes"] += 1

        expected = habit["strength"]
        prediction_error = reward - expected
        habit["strength"] = max(
            0.0,
            min(1.0, habit["strength"] + learning_rate * prediction_error),
        )

        return habit["strength"]

    def check_automated_response(self, stimulus: str) -> Optional[str]:
        stimulus_lower = stimulus.lower()

        if stimulus_lower in self.automated_responses:
            return self.automated_responses[stimulus_lower]

        for habit_id, habit in self.habits.items():
            if habit["stimulus"].lower() in stimulus_lower and habit["strength"] > 0.7:
                return habit["response"]

        return None


class MemoryConsolidator:
    def __init__(
        self,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        procedural: ProceduralMemory,
    ):
        self.episodic = episodic
        self.semantic = semantic
        self.procedural = procedural
        self.consolidation_queue: List[str] = []
        self.dream_reports: List[str] = []
        self.consolidation_count = 0

    def queue_for_consolidation(self, episode_id: str) -> None:
        if episode_id not in self.consolidation_queue:
            self.consolidation_queue.append(episode_id)

    def consolidate(self) -> None:
        if not self.consolidation_queue:
            return

        important_episodes = self._select_important_episodes()

        for episode_id in important_episodes:
            episode = next(
                (t for t in self.episodic.episodes if t.trace_id == episode_id),
                None,
            )
            if not episode:
                continue

            self._extract_semantics(episode)
            self._extract_procedures(episode)

        self._generate_dreams(important_episodes)

        self.consolidation_queue = []
        self.consolidation_count += 1

    def _select_important_episodes(self, max_count: int = 10) -> List[str]:
        scored = []
        for episode_id in self.consolidation_queue:
            episode = next(
                (t for t in self.episodic.episodes if t.trace_id == episode_id),
                None,
            )
            if episode:
                score = episode.strength
                scored.append((score, episode_id))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:max_count]]

    def _extract_semantics(self, episode: MemoryTrace) -> None:
        words = episode.content.lower().split()
        unique_words = list(set(words))

        for word in unique_words[:10]:
            if word not in self.semantic.concepts:
                self.semantic.encode_concept(
                    word,
                    f"Concept derived from episode: {episode.content[:50]}",
                )

        for i in range(len(unique_words) - 1):
            self.semantic.encode_fact(
                unique_words[i],
                "related_to",
                unique_words[i + 1],
                confidence=0.5,
            )

    def _extract_procedures(self, episode: MemoryTrace) -> None:
        content = episode.content.lower()
        if "learn" in content or "skill" in content or "how to" in content:
            skill_id = f"skill_{uuid.uuid4().hex[:8]}"
            self.procedural.encode_skill(
                skill_id,
                f"Skill from episode",
                ["Step 1: Analyze context", "Step 2: Execute action"],
                context_triggers=[content[:30]],
            )

        if "habit" in content or "always" in content or "usually" in content:
            habit_id = f"habit_{uuid.uuid4().hex[:8]}"
            self.procedural.encode_habit(
                habit_id,
                content[:30],
                "Automatic response",
            )

    def _generate_dreams(self, episode_ids: List[str]) -> None:
        if len(episode_ids) < 2:
            return

        selected = episode_ids[:3]
        episodes = [
            t for t in self.episodic.episodes
            if t.trace_id in selected
        ]

        if len(episodes) >= 2:
            dream_content = f"Dream: " + " | ".join(
                e.content[:30] for e in sorted(episodes, key=lambda x: x.timestamp)
            )
            self.dream_reports.append(dream_content)

    def get_dream_report(self, recent_count: int = 5) -> List[str]:
        return self.dream_reports[-recent_count:]
