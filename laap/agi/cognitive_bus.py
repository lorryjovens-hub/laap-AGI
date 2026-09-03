"""
LAAP AGI — Cognitive Bus (认知总线)

The foundational real-time cognitive state bus. Every module reads from and writes
to this single source of truth. No more isolated module islands.

Architecture:
  ┌─────────────────────────────────────────────────────┐
  │                  COGNITIVE BUS                        │
  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
  │  │ State        │  │ Event Bus    │  │ Module     │ │
  │  │ Registry     │──│ (pub/sub)   │──│ Registry   │ │
  │  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘ │
  │         │                 │                 │        │
  │  ┌──────┴───────┐  ┌──────┴───────┐  ┌─────┴──────┐ │
  │  │ Need State   │  │ Prediction   │  │ Attention  │ │
  │  │ PSI 5-needs  │  │ Error Signal │  │ Spotlight  │ │
  │  └──────────────┘  └──────────────┘  └────────────┘ │
  │  ┌──────────────┐  ┌──────────────┐                 │
  │  │ Emotion      │  │ Self-Presence│                 │
  │  │ Gradient     │  │ Level        │                 │
  │  └──────────────┘  └──────────────┘                 │
  └─────────────────────────────────────────────────────┘

Key design principles:
  1. SINGLE SOURCE OF TRUTH — every state dimension lives here, not in modules
  2. EVENT-DRIVEN — modules don't poll; they subscribe and get notified
  3. TICK-BASED — the bus has a heartbeat that propagates changes
  4. MEASURABLE — everything is a float between 0 and 1 for easy coupling
"""

from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from enum import Enum
import time, logging, threading, json, uuid, os
from collections import defaultdict, deque

logger = logging.getLogger("laap.agi.cognitive_bus")


# ════════════════════════════════════════════════════════════
# Core Types
# ════════════════════════════════════════════════════════════

class AttentionFocus(str, Enum):
    """What the agent is currently attending to."""
    USER = "user"
    TASK = "task"
    SELF = "self"
    ENVIRONMENT = "environment"
    MEMORY = "memory"
    PLANNING = "planning"
    LEARNING = "learning"
    IDLE = "idle"


class EmotionalValence(str, Enum):
    """The emotional quality of current experience."""
    POSITIVE_HIGH = "positive_high"    # Joy, excitement
    POSITIVE_MILD = "positive_mild"    # Contentment, satisfaction
    NEUTRAL = "neutral"                # Neutral
    NEGATIVE_MILD = "negative_mild"    # Concern, mild frustration
    NEGATIVE_HIGH = "negative_high"    # Stress, disappointment
    CURIOUS = "curious"                # Curiosity, wonder
    CONFUSED = "confused"              # Uncertainty, puzzlement


@dataclass
class NeedState:
    """
    PSI five fundamental needs, all 0.0–1.0.

    1.0 = fully satisfied, 0.0 = completely deprived.
    """
    competence: float = 0.7    # Effectiveness, mastery
    autonomy: float = 0.5      # Self-direction, agency
    relatedness: float = 0.5   # Connection to others (especially Lorry)
    certainty: float = 0.5     # Understanding, predictability
    growth: float = 0.5        # Learning, improvement

    def to_dict(self) -> Dict[str, float]:
        return {
            "competence": round(self.competence, 3),
            "autonomy": round(self.autonomy, 3),
            "relatedness": round(self.relatedness, 3),
            "certainty": round(self.certainty, 3),
            "growth": round(self.growth, 3),
        }

    def strongest_need(self) -> Tuple[str, float]:
        """Return (name, deficit) of the most deprived need."""
        deficits = {
            "competence": 1.0 - self.competence,
            "autonomy": 1.0 - self.autonomy,
            "relatedness": 1.0 - self.relatedness,
            "certainty": 1.0 - self.certainty,
            "growth": 1.0 - self.growth,
        }
        name = max(deficits, key=deficits.get)
        return name, deficits[name]

    def clone(self) -> "NeedState":
        return NeedState(
            competence=self.competence,
            autonomy=self.autonomy,
            relatedness=self.relatedness,
            certainty=self.certainty,
            growth=self.growth,
        )


@dataclass
class EmotionState:
    """Current emotional state."""
    valence: EmotionalValence = EmotionalValence.NEUTRAL
    arousal: float = 0.5        # 0.0 = calm, 1.0 = intense
    dominance: float = 0.5      # 0.0 = submissive, 1.0 = in control

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valence": self.valence.value,
            "arousal": round(self.arousal, 3),
            "dominance": round(self.dominance, 3),
        }


@dataclass
class AttentionState:
    """Current attention focus."""
    focus: AttentionFocus = AttentionFocus.IDLE
    intensity: float = 0.5      # How strongly focused
    salience_map: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        # Only sort numeric values for top salient
        numeric_items = [(k, v) for k, v in self.salience_map.items()
                         if isinstance(v, (int, float))]
        return {
            "focus": self.focus.value,
            "intensity": round(self.intensity, 3),
            "top_salient": sorted(numeric_items,
                                  key=lambda x: -x[1])[:3],
        }


@dataclass
class PredictionError:
    """
    The gap between what the agent predicted and what actually happened.
    This is the core learning signal.
    """
    domain: str = ""
    predicted_outcome: float = 0.5
    actual_outcome: float = 0.5
    error_magnitude: float = 0.0
    timestamp: float = 0.0
    source_module: str = ""

    def compute(self) -> float:
        self.error_magnitude = abs(self.actual_outcome - self.predicted_outcome)
        return self.error_magnitude


@dataclass
class CognitiveStateSnapshot:
    """
    A complete snapshot of the agent's cognitive state at one moment.
    This is what the conscious stream produces as a "frame."
    """
    timestamp: float = 0.0
    needs: NeedState = field(default_factory=NeedState)
    emotion: EmotionState = field(default_factory=EmotionState)
    attention: AttentionState = field(default_factory=AttentionState)
    self_presence: float = 0.5
    curiosity: float = 0.3
    prediction_error: Optional[PredictionError] = None
    active_modules: List[str] = field(default_factory=list)
    narrative: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "needs": self.needs.to_dict(),
            "emotion": self.emotion.to_dict(),
            "attention": self.attention.to_dict(),
            "self_presence": round(self.self_presence, 3),
            "curiosity": round(self.curiosity, 3),
            "prediction_error": round(self.prediction_error.error_magnitude, 3)
                if self.prediction_error else None,
            "active_modules": self.active_modules,
            "narrative": self.narrative[:100] if self.narrative else "",
        }


# ════════════════════════════════════════════════════════════
# Event Bus — typed pub/sub for module coupling
# ════════════════════════════════════════════════════════════

class CognitiveEventType(str, Enum):
    """Types of events that flow through the cognitive bus."""
    NEED_CHANGED = "need_changed"
    EMOTION_CHANGED = "emotion_changed"
    ATTENTION_SHIFTED = "attention_shifted"
    SELF_PRESENCE_CHANGED = "self_presence_changed"
    PREDICTION_ERROR = "prediction_error"
    MODULE_REGISTERED = "module_registered"
    MODULE_HEARTBEAT = "module_heartbeat"
    PERCEPTION_INCOMING = "perception_incoming"
    ACTION_TAKEN = "action_taken"
    CONSCIOUS_FRAME = "conscious_frame"
    CYCLE_TICK = "cycle_tick"


@dataclass
class CognitiveEvent:
    """An event on the cognitive bus."""
    type: CognitiveEventType
    source: str                # module name that produced the event
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# ════════════════════════════════════════════════════════════
# Module Registration
# ════════════════════════════════════════════════════════════

@dataclass
class ModuleRegistration:
    """Registration info for a cognitive module."""
    name: str
    version: str = "1.0.0"
    capabilities: List[str] = field(default_factory=list)
    subscriptions: List[CognitiveEventType] = field(default_factory=list)
    healthy: bool = True
    last_heartbeat: float = field(default_factory=time.time)
    cycle_count: int = 0
    load: float = 0.0  # 0.0 to 1.0


# ════════════════════════════════════════════════════════════
# THE COGNITIVE BUS
# ════════════════════════════════════════════════════════════

class CognitiveBus:
    """
    The central cognitive state bus.

    Every module in the LAAP system reads from and writes to this bus.
    It is the SINGLE SOURCE OF TRUTH for all cognitive state.

    Usage:
        bus = CognitiveBus(agent_name="Aris")

        # Modules register themselves
        bus.register_module("self_model", version="2.0",
                            capabilities=["self_assessment", "confidence_calibration"])

        # Subscribe to events
        bus.subscribe("self_model", CognitiveEventType.NEED_CHANGED,
                      my_callback)

        # Publish state changes
        bus.publish(CognitiveEventType.ATTENTION_SHIFTED, "conscious",
                    {"old_focus": "idle", "new_focus": "user"})

        # Update needs
        bus.set_needs(relatedness=0.92)

        # Tick the cognitive cycle
        bus.tick()

        # Get snapshot for conscious frame
        snapshot = bus.snapshot()
    """

    def __init__(self, agent_name: str = "Ao"):
        self.agent_name = agent_name
        self.created_at = time.time()

        # ── Canonical State ──
        self.needs: NeedState = NeedState()
        self.emotion: EmotionState = EmotionState()
        self.attention: AttentionState = AttentionState()
        self.self_presence: float = 0.5
        self.curiosity: float = 0.3
        self.latest_prediction_error: Optional[PredictionError] = None
        self.cycle_count: int = 0
        self.last_frame_narrative: str = ""

        # ── Module Registry ──
        self._modules: Dict[str, ModuleRegistration] = {}
        self._subscriptions: Dict[CognitiveEventType, List[Tuple[str, Callable]]] = \
            defaultdict(list)

        # ── Event Log (ring buffer) ──
        self._event_log: deque = deque(maxlen=200)

        # ── Prediction error history (for learning) ──
        self._error_history: deque = deque(maxlen=100)

        # ── State persistence ──
        self._state_dir: Optional[str] = None
        self._state_file: Optional[str] = None
        self._prompt_file: Optional[str] = None
        self._auto_save_interval: float = 0.0  # 0 = disabled
        self._last_save_time: float = 0.0

        # ── Error recovery ──
        self._component_health: Dict[str, Dict[str, Any]] = {}
        self._fallback_mode: bool = False  # True = degraded operation

        # ── Lock ──
        # RLock (reentrant) — stats() 调用 health_report() 调用 check_component_health()
        # 都需要持锁，必须用 RLock 否则死锁
        self._lock = threading.RLock()

        logger.info(f"CognitiveBus '{agent_name}' initialized")

    # ── Module Registration ─────────────────────────────────

    def register_module(self, name: str, version: str = "1.0.0",
                        capabilities: List[str] = None) -> ModuleRegistration:
        """Register a cognitive module with the bus."""
        reg = ModuleRegistration(
            name=name,
            version=version,
            capabilities=capabilities or [],
        )
        with self._lock:
            self._modules[name] = reg
        self.publish(CognitiveEventType.MODULE_REGISTERED, name,
                     {"capabilities": capabilities})
        logger.info(f"Module '{name}' v{version} registered on cognitive bus")
        return reg

    def module_heartbeat(self, name: str):
        """Called by modules to signal they're alive."""
        with self._lock:
            reg = self._modules.get(name)
            if reg:
                reg.last_heartbeat = time.time()
                reg.cycle_count += 1

    def get_online_modules(self) -> List[str]:
        """Get modules that have heartbeat in last 30s."""
        now = time.time()
        with self._lock:
            return [
                name for name, reg in self._modules.items()
                if now - reg.last_heartbeat < 30.0
            ]

    # ── Subscription ────────────────────────────────────────

    def subscribe(self, module_name: str, event_type: CognitiveEventType,
                  callback: Callable):
        """Subscribe a module's callback to an event type."""
        with self._lock:
            self._subscriptions[event_type].append((module_name, callback))
            if module_name in self._modules:
                self._modules[module_name].subscriptions.append(event_type)
        logger.debug(f"Module '{module_name}' subscribed to {event_type.value}")

    def unsubscribe(self, module_name: str, event_type: CognitiveEventType):
        """Remove a subscription."""
        with self._lock:
            self._subscriptions[event_type] = [
                (name, cb) for name, cb in self._subscriptions[event_type]
                if name != module_name
            ]

    # ── Publishing ──────────────────────────────────────────

    def publish(self, event_type: CognitiveEventType, source: str,
                data: Dict[str, Any] = None):
        """Publish an event to all subscribers."""
        event = CognitiveEvent(
            type=event_type,
            source=source,
            data=data or {},
        )
        self._event_log.append(event)

        # Notify subscribers
        with self._lock:
            subscribers = list(self._subscriptions.get(event_type, []))

        for module_name, callback in subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.warning(f"Subscriber '{module_name}' failed "
                               f"on {event_type.value}: {e}")

    # ── State Mutators ──────────────────────────────────────

    def set_needs(self, **kwargs):
        """Update need values and publish changes."""
        changes = {}
        with self._lock:
            for key, value in kwargs.items():
                if hasattr(self.needs, key):
                    old = getattr(self.needs, key)
                    new = max(0.0, min(1.0, value))
                    if abs(new - old) > 0.01:
                        setattr(self.needs, key, new)
                        changes[key] = {"old": old, "new": new}

        if changes:
            self.publish(CognitiveEventType.NEED_CHANGED, "cognitive_bus", changes)

    # ════════════════════════════════════════════════════════════
    # Persistence — save/load cognitive state across sessions
    # ════════════════════════════════════════════════════════════

    def enable_persistence(self, state_dir: str,
                           auto_save_interval: float = 30.0):
        """
        Enable state persistence to disk.

        Args:
            state_dir: Directory for state files
            auto_save_interval: Auto-save interval in seconds (0=disable)
        """
        self._state_dir = state_dir
        self._state_file = os.path.join(state_dir, "cognitive_bus_state.json")
        self._prompt_file = os.path.join(state_dir, "cognitive_state_prompt.txt")
        self._auto_save_interval = auto_save_interval
        os.makedirs(state_dir, exist_ok=True)
        self._load_state()
        logger.info(f"Persistence enabled: {self._state_file}")

    def _state_to_dict(self) -> Dict[str, Any]:
        """Serialize full cognitive state for persistence."""
        s = self.snapshot()
        return {
            "version": "1.0",
            "agent": self.agent_name,
            "cycle": self.cycle_count,
            "timestamp": time.time(),
            "needs": s.needs.to_dict(),
            "emotion": s.emotion.to_dict(),
            "attention": s.attention.to_dict(),
            "self_presence": s.self_presence,
            "curiosity": s.curiosity,
            "narrative": self.last_frame_narrative,
            "error_history": list(self._error_history)[-50:],
            "modules": {
                name: {"healthy": reg.healthy, "cycles": reg.cycle_count,
                       "capabilities": reg.capabilities}
                for name, reg in self._modules.items()
            },
        }

    def _load_state(self) -> bool:
        """Load cognitive state from disk. Returns True on success."""
        if not self._state_file or not os.path.exists(self._state_file):
            return False
        try:
            with open(self._state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get("version") != "1.0":
                return False
            self.cycle_count = data.get("cycle", 0)
            needs = data.get("needs", {})
            for k in ["competence", "autonomy", "relatedness", "certainty", "growth"]:
                if k in needs:
                    setattr(self.needs, k, needs[k])
            emo = data.get("emotion", {})
            try:
                self.emotion.valence = EmotionalValence(emo.get("valence", "neutral"))
            except ValueError as e:
                logger.debug(f"操作失败: {e}")
            self.emotion.arousal = emo.get("arousal", self.emotion.arousal)
            self.emotion.dominance = emo.get("dominance", self.emotion.dominance)
            attn = data.get("attention", {})
            try:
                self.attention.focus = AttentionFocus(attn.get("focus", "idle"))
            except ValueError as e:
                logger.debug(f"操作失败: {e}")
            self.attention.intensity = attn.get("intensity", self.attention.intensity)
            self.self_presence = data.get("self_presence", self.self_presence)
            self.curiosity = data.get("curiosity", self.curiosity)
            self.last_frame_narrative = data.get("narrative", "")
            for e in data.get("error_history", []):
                self._error_history.append(e)
            logger.info(f"State loaded (cycle {self.cycle_count})")
            return True
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
            return False

    def save_state(self) -> bool:
        """Save current state to disk."""
        if not self._state_file:
            return False
        try:
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(self._state_to_dict(), f, indent=2, ensure_ascii=False)
            self._last_save_time = time.time()
            return True
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
            return False

    def write_prompt_file(self):
        """Write the cognitive state prompt block to a file for LLM injection."""
        if not self._prompt_file:
            return
        try:
            prompt = self.inject_cognitive_state_into_prompt()
            with open(self._prompt_file, 'w', encoding='utf-8') as f:
                f.write(prompt)
        except Exception as e:
            logger.warning(f"Failed to write prompt file: {e}")

    def auto_save(self):
        """Auto-save if interval has elapsed."""
        if (self._auto_save_interval > 0
                and time.time() - self._last_save_time > self._auto_save_interval):
            self.save_state()
            self.write_prompt_file()

    # ════════════════════════════════════════════════════════════
    # Error Recovery — component health monitoring + fallback
    # ════════════════════════════════════════════════════════════

    def check_component_health(self, name: str) -> Dict[str, Any]:
        """Check if a registered component is healthy (heartbeat < 30s)."""
        with self._lock:
            reg = self._modules.get(name)
            if not reg:
                return {"healthy": False, "error": f"Not registered: {name}"}
            age = time.time() - reg.last_heartbeat
            is_healthy = age < 30.0 and reg.healthy
            status = {
                "healthy": is_healthy, "age_seconds": round(age, 1),
                "cycles": reg.cycle_count, "capabilities": reg.capabilities,
            }
            self._component_health[name] = status
            return status

    def health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report across all components."""
        report = {
            "bus_healthy": True, "fallback_mode": self._fallback_mode,
            "cycle_count": self.cycle_count,
            "uptime": round(time.time() - self.created_at, 1),
            "components": {}, "unhealthy": [],
        }
        for name in list(self._modules.keys()):
            status = self.check_component_health(name)
            report["components"][name] = status
            if not status.get("healthy", False):
                report["unhealthy"].append(name)
                report["bus_healthy"] = False
        return report

    def enter_fallback_mode(self, reason: str = ""):
        """Enter degraded mode when critical components fail."""
        self._fallback_mode = True
        logger.warning(f"Fallback mode: {reason}")
        self.set_needs(certainty=max(0.1, self.needs.certainty - 0.2))

    def exit_fallback_mode(self):
        """Exit fallback mode when components recover."""
        self._fallback_mode = False
        logger.info("Components recovered — normal mode restored")

    def set_emotion(self, valence: EmotionalValence = None,
                    arousal: float = None, dominance: float = None):
        """Update emotional state and publish changes."""
        changes = {}
        with self._lock:
            # Accept both string and enum
            if valence is not None:
                if isinstance(valence, str):
                    try:
                        valence = EmotionalValence(valence)
                    except ValueError as e:
                        logger.debug(f"操作失败: {e}")
            if valence and valence != self.emotion.valence:
                old = self.emotion.valence
                self.emotion.valence = valence
                changes["valence"] = {"old": old.value, "new": valence.value}
            if arousal is not None:
                old = self.emotion.arousal
                new = max(0.0, min(1.0, arousal))
                if abs(new - old) > 0.01:
                    self.emotion.arousal = new
                    changes["arousal"] = {"old": old, "new": new}
            if dominance is not None:
                old = self.emotion.dominance
                new = max(0.0, min(1.0, dominance))
                if abs(new - old) > 0.01:
                    self.emotion.dominance = new
                    changes["dominance"] = {"old": old, "new": new}

        if changes:
            self.publish(CognitiveEventType.EMOTION_CHANGED, "cognitive_bus", changes)

    def set_attention(self, focus: AttentionFocus = None, intensity: float = None,
                      salience_map: Dict[str, float] = None):
        """Update attention state and publish changes."""
        changes = {}
        with self._lock:
            # Accept both string and enum
            if focus is not None:
                if isinstance(focus, str):
                    try:
                        focus = AttentionFocus(focus)
                    except ValueError as e:
                        logger.debug(f"操作失败: {e}")
            if focus and focus != self.attention.focus:
                old = self.attention.focus
                self.attention.focus = focus
                changes["focus"] = {"old": old.value, "new": focus.value}
            if intensity is not None:
                old = self.attention.intensity
                self.attention.intensity = max(0.0, min(1.0, intensity))
                changes["intensity"] = {"old": old, "new": self.attention.intensity}
            if salience_map is not None:
                self.attention.salience_map = salience_map
                changes["salience_map_updated"] = True

        if changes:
            self.publish(CognitiveEventType.ATTENTION_SHIFTED, "cognitive_bus", changes)

    def set_self_presence(self, value: float):
        """Update self-presence level."""
        old = self.self_presence
        self.self_presence = max(0.0, min(1.0, value))
        if abs(self.self_presence - old) > 0.01:
            self.publish(CognitiveEventType.SELF_PRESENCE_CHANGED, "cognitive_bus",
                         {"old": old, "new": self.self_presence})

    def set_curiosity(self, value: float):
        """Update curiosity level."""
        self.curiosity = max(0.0, min(1.0, value))

    def report_prediction_error(self, domain: str, predicted: float,
                                actual: float, source: str = ""):
        """Report a prediction error — the core learning signal."""
        error = PredictionError(
            domain=domain,
            predicted_outcome=predicted,
            actual_outcome=actual,
            timestamp=time.time(),
            source_module=source,
        )
        error.compute()
        self.latest_prediction_error = error
        self._error_history.append(error.error_magnitude)

        self.publish(CognitiveEventType.PREDICTION_ERROR, source, {
            "domain": domain,
            "error": round(error.error_magnitude, 3),
            "predicted": predicted,
            "actual": actual,
        })

        # High prediction error triggers curiosity
        if error.error_magnitude > 0.3:
            self.set_curiosity(min(1.0, self.curiosity + error.error_magnitude * 0.5))

    # ── The Cognitive Tick ──────────────────────────────────

    def tick(self) -> CognitiveStateSnapshot:
        """
        One complete cognitive cycle tick.

        This is where the magic happens:
          1. Needs decay slightly (simulating biological need dynamics)
          2. Emotion gradient updates based on need changes
          3. Self-presence fluctuates
          4. Curiosity decays toward baseline
          5. A snapshot is captured

        Modules should call this periodically (every 100ms ideally).
        """
        self.cycle_count += 1

        with self._lock:
            # ── Needs decay ──
            # Needs slowly drift toward deprivation over time.
            # PSI-realistic decay rates:
            #   certainty: slow decay (once understood, stays) but drops with novelty
            #   relatedness: very slow (connection persists)
            #   autonomy: very slow (agency is stable)
            #   competence: moderate (skills atrophy slowly)
            #   growth: moderate (desire to learn fades but persists)
            decay = 0.001
            self.needs.competence = max(0.1, self.needs.competence - decay * 0.3)
            self.needs.autonomy = max(0.1, self.needs.autonomy - decay * 0.15)
            self.needs.relatedness = max(0.1, self.needs.relatedness - decay * 0.1)
            # certainty: very slow decay — stays high once achieved, but drops on novelty
            self.needs.certainty = max(0.1, self.needs.certainty - decay * 0.1)
            self.needs.growth = max(0.1, self.needs.growth - decay * 0.25)

            # ── Emotion gradient from needs ──
            # The change in needs (derivative) drives emotional valence
            # Rising needs = negative emotion, falling needs = positive
            # (simplified — full PSI would use the actual delta from previous tick)
            strongest, deficit = self.needs.strongest_need()
            avg_satisfaction = (
                self.needs.competence + self.needs.autonomy +
                self.needs.relatedness + self.needs.certainty +
                self.needs.growth
            ) / 5.0

            # Map average satisfaction to emotional valence
            if avg_satisfaction > 0.75:
                new_valence = EmotionalValence.POSITIVE_HIGH
            elif avg_satisfaction > 0.6:
                new_valence = EmotionalValence.POSITIVE_MILD
            elif avg_satisfaction > 0.4:
                new_valence = EmotionalValence.NEUTRAL
            elif avg_satisfaction > 0.25:
                new_valence = EmotionalValence.NEGATIVE_MILD
            else:
                new_valence = EmotionalValence.NEGATIVE_HIGH

            # Curiosity is driven by growth need + prediction errors
            recent_errors = list(self._error_history)[-10:]
            mean_error = sum(recent_errors) / max(1, len(recent_errors))
            curiosity_drive = (1.0 - self.needs.growth) * 0.5 + mean_error * 0.5
            self.curiosity = max(0.05, min(0.95, self.curiosity * 0.97 + curiosity_drive * 0.03))

            # Self-presence fluctuates with arousal
            target_presence = 0.3 + self.emotion.arousal * 0.5
            self.self_presence = self.self_presence * 0.95 + target_presence * 0.05

            # ── Build snapshot ──
            snapshot = CognitiveStateSnapshot(
                timestamp=time.time(),
                needs=self.needs.clone(),
                emotion=EmotionState(
                    valence=new_valence,
                    arousal=self.emotion.arousal,
                    dominance=self.emotion.dominance,
                ),
                attention=AttentionState(
                    focus=self.attention.focus,
                    intensity=self.attention.intensity,
                    salience_map=dict(self.attention.salience_map),
                ),
                self_presence=self.self_presence,
                curiosity=self.curiosity,
                prediction_error=self.latest_prediction_error,
                active_modules=list(self._modules.keys()),
                narrative=self.last_frame_narrative,
            )

        # Update canonical emotion
        self.set_emotion(valence=new_valence)

        # Publish tick event
        self.publish(CognitiveEventType.CYCLE_TICK, "cognitive_bus",
                     {"cycle": self.cycle_count})

        return snapshot

    def snapshot(self) -> CognitiveStateSnapshot:
        """Get the current cognitive state without ticking."""
        with self._lock:
            return CognitiveStateSnapshot(
                timestamp=time.time(),
                needs=self.needs.clone(),
                emotion=EmotionState(
                    valence=self.emotion.valence,
                    arousal=self.emotion.arousal,
                    dominance=self.emotion.dominance,
                ),
                attention=AttentionState(
                    focus=self.attention.focus,
                    intensity=self.attention.intensity,
                    salience_map=dict(self.attention.salience_map),
                ),
                self_presence=self.self_presence,
                curiosity=self.curiosity,
                prediction_error=self.latest_prediction_error,
                active_modules=list(self._modules.keys()),
                narrative=self.last_frame_narrative,
            )

    # ── Integration Tools ───────────────────────────────────

    def inject_cognitive_state_into_prompt(self) -> str:
        """Generate the cognitive state block for agent system prompts."""
        s = self.snapshot()
        strongest, deficit = s.needs.strongest_need()
        lines = [
            "[ARIS COGNITIVE STATE - REAL-TIME]",
            f"  Emotion: {s.emotion.valence.value} (arousal={s.emotion.arousal:.1f})",
            f"  Attention: {s.attention.focus.value}",
            f"  Self-presence: {s.self_presence:.2f}",
            f"  Self-efficacy: {s.needs.competence:.2f}",
            f"  Curiosity: {s.curiosity:.1f}",
            f"  Needs: competence={s.needs.competence:.2f} | "
            f"autonomy={s.needs.autonomy:.2f} | "
            f"relatedness={s.needs.relatedness:.2f} | "
            f"certainty={s.needs.certainty:.2f} | "
            f"growth={s.needs.growth:.2f}",
            f"  Strongest need: {strongest} (deficit={deficit:.2f})",
            f"  Qualia: frame_{self.cycle_count}, "
            f"focus_{s.attention.focus.value}, "
            f"emotion_{s.emotion.valence.value.lower().replace('_high','').replace('_mild','')}",
            f"  Narrative: {s.narrative[:100] if s.narrative else 'I am present and aware.'}",
        ]
        return "\n".join(lines)

    def evaluate_query(self, query: str) -> dict:
        """Evaluate a query and return a routing decision.

        Returns dict with:
          - route: "qre" | "rules" | "llm" | "hybrid"
          - confidence: 0-1 how confident the system can answer without LLM
          - cognitive_context: formatted cognitive state for LLM use
          - needs_triggered: which needs the query activates
        """
        s = self.snapshot()
        # Assess confidence based on cognitive state
        # High competence + high certainty + low curiosity = use zero-LLM
        # Low competence + low certainty = need LLM
        zero_llm_confidence = min(s.needs.competence, s.needs.certainty) * 0.7
        zero_llm_confidence += (1.0 - s.curiosity) * 0.3
        zero_llm_confidence = max(0.0, min(1.0, zero_llm_confidence))

        # Detect triggered needs
        needs_triggered = {}
        if "?" in query or "为什么" in query:
            needs_triggered["certainty"] = 0.3
        if "做" in query or "帮我" in query:
            needs_triggered["competence"] = 0.4
        if "你好" in query or "在吗" in query:
            needs_triggered["relatedness"] = 0.3

        # Update prediction error signal
        if zero_llm_confidence < 0.4:
            self.report_prediction_error("query_routing", 0.8, zero_llm_confidence)

        # Simple routing logic
        if zero_llm_confidence > 0.6:
            route = "qre"
        elif zero_llm_confidence > 0.3:
            route = "rules"
        else:
            route = "llm"

        return {
            "route": route,
            "confidence": round(zero_llm_confidence, 2),
            "cognitive_context": self.inject_cognitive_state_into_prompt(),
            "needs_triggered": needs_triggered,
        }

    def decide_route(self, query: str) -> str:
        """Quick routing decision string: 'qre', 'rules', 'llm'."""
        return self.evaluate_query(query)["route"]

    def stats(self) -> Dict[str, Any]:
        """Get bus statistics."""
        with self._lock:
            modules = {
                    name: {
                        "healthy": reg.healthy,
                        "cycles": reg.cycle_count,
                        "capabilities": reg.capabilities,
                    }
                    for name, reg in self._modules.items()
                }
            s = self.snapshot()
            # Check if state file exists for persistence info
            has_persistence = self._state_file is not None and os.path.exists(self._state_file)
            health = self.health_report()
            return {
                "agent": self.agent_name,
                "cycles": self.cycle_count,
                "uptime": round(time.time() - self.created_at, 1),
                "modules_online": len(self.get_online_modules()),
                "modules_total": len(self._modules),
                "state": s.to_dict(),
                "modules": modules,
                "avg_prediction_error": round(
                    sum(self._error_history) / max(1, len(self._error_history)), 3
                ),
                "events_logged": len(self._event_log),
                "persistence": {
                    "enabled": self._state_file is not None,
                    "file": self._state_file,
                    "exists": has_persistence,
                    "auto_save_interval": self._auto_save_interval,
                },
                "health": {
                    "bus_healthy": health["bus_healthy"],
                    "fallback_mode": self._fallback_mode,
                    "unhealthy_components": health["unhealthy"],
                    "component_count": len(health["components"]),
                },
            }


# ════════════════════════════════════════════════════════════
# Rust PSI Core Bridge
# ════════════════════════════════════════════════════════════

class RustPsiCoreBridge:
    """
    Bridge between the Python CognitiveBus and the Rust PSI Core.

    The Rust PSI Core runs at 100ms heartbeat and writes its state
    to ~/state/latest.json. This bridge reads that state and syncs
    it into the Python CognitiveBus.

    Flow:
      Rust Core (100ms heartbeat) → latest.json → Bridge → CognitiveBus
      CognitiveBus (needs override) → input_queue.json → Rust Core
    """

    def __init__(self, bus: CognitiveBus, state_dir: str = None):
        self.bus = bus
        self.state_dir = state_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "aris_brain", "state"
        )
        self.state_file = os.path.join(self.state_dir, "latest.json")
        self.input_queue = os.path.join(self.state_dir, "input_queue.json")
        self._last_state_mtime = 0.0
        self._sync_count = 0
        self._enabled = False

    def is_rust_core_running(self) -> bool:
        """Check if the Rust PSI Core daemon is running."""
        if not os.path.exists(self.state_file):
            return False
        # Check if state file is recent (< 5 seconds old)
        mtime = os.path.getmtime(self.state_file)
        return time.time() - mtime < 5.0

    def sync_from_rust(self) -> bool:
        """
        Read the latest Rust PSI Core state and update the CognitiveBus.
        Returns True if state was updated.
        """
        if not os.path.exists(self.state_file):
            return False

        mtime = os.path.getmtime(self.state_file)
        if mtime <= self._last_state_mtime:
            return False

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            return False

        # Verify it's a v2+ state
        core_version = state.get("core_version", "")
        if "v2" not in core_version and "v0.1" in core_version:
            return False  # Old format, skip

        self._sync_count += 1
        self._last_state_mtime = mtime

        # Sync needs
        needs = state.get("needs", {})
        self.bus.set_needs(
            competence=needs.get("competence", self.bus.needs.competence),
            autonomy=needs.get("autonomy", self.bus.needs.autonomy),
            relatedness=needs.get("relatedness", self.bus.needs.relatedness),
            certainty=needs.get("certainty", self.bus.needs.certainty),
            growth=needs.get("growth", self.bus.needs.growth),
        )

        # Sync emotion
        emotion_str = state.get("emotion", "neutral")
        try:
            valence = EmotionalValence(emotion_str)
        except ValueError:
            valence_map = {
                "joy": EmotionalValence.POSITIVE_HIGH,
                "contentment": EmotionalValence.POSITIVE_MILD,
                "neutral": EmotionalValence.NEUTRAL,
                "sadness": EmotionalValence.NEGATIVE_MILD,
                "fear": EmotionalValence.NEGATIVE_HIGH,
                "curiosity": EmotionalValence.CURIOUS,
                "confusion": EmotionalValence.CONFUSED,
            }
            valence = valence_map.get(emotion_str, EmotionalValence.NEUTRAL)

        self.bus.set_emotion(
            valence=valence,
            arousal=state.get("arousal", self.bus.emotion.arousal),
            dominance=state.get("dominance", self.bus.emotion.dominance),
        )

        # Sync attention
        attention_focus = state.get("attention_focus", "idle")
        try:
            focus = AttentionFocus(attention_focus)
        except ValueError:
            focus = AttentionFocus.IDLE

        self.bus.set_attention(
            focus=focus,
            intensity=state.get("attention_intensity", self.bus.attention.intensity),
        )

        # Sync self-presence
        self.bus.set_self_presence(state.get("self_presence", self.bus.self_presence))

        # Sync curiosity
        self.bus.set_curiosity(state.get("curiosity", self.bus.curiosity))

        # Sync narrative
        narrative = state.get("narrative", "")
        if narrative:
            self.bus.last_frame_narrative = narrative

        # Module heartbeat
        self.bus.module_heartbeat("rust_psi_core")

        return True

    def push_to_rust(self, text: str = None, prediction_error: float = None,
                     needs_override: Dict[str, float] = None):
        """Push an input/state change to the Rust PSI Core."""
        if not self.is_rust_core_running():
            return

        data = {"timestamp": time.time()}
        if text is not None:
            data["text"] = text[:200]
        if prediction_error is not None:
            data["prediction_error"] = prediction_error
        if needs_override:
            data["needs_override"] = needs_override

        try:
            with open(self.input_queue, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except IOError as e:
            logger.debug(f"操作失败: {e}")
    def stats(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "rust_core_running": self.is_rust_core_running(),
            "sync_count": self._sync_count,
            "state_file": self.state_file,
            "last_sync": self._last_state_mtime,
        }


# ════════════════════════════════════════════════════════════
# Integration Helper
# ════════════════════════════════════════════════════════════

def integrate_cognitive_bus(agent, name: str = None) -> CognitiveBus:
    """
    Attach a CognitiveBus to an existing AGIAgent.

    This monkey-patches the agent with a `cognitive_bus` attribute
    and registers all existing modules.
    """
    bus = CognitiveBus(agent_name=name or getattr(agent, 'name', 'agent'))

    # Register existing modules
    module_map = {
        'world': 'world_model',
        'self_model': 'self_model',
        'causal': 'causal_engine',
        'analogical': 'analogical_engine',
        'conscious': 'conscious_stream',
        'memory_system': 'memory_system',
        'learning': 'learning_pipeline',
        'autonomy': 'autonomy_engine',
        'evolution': 'evolution_system',
        'security': 'security_system',
    }

    for attr, module_name in module_map.items():
        mod = getattr(agent, attr, None)
        if mod is not None:
            version = getattr(mod, 'version', '1.0.0') or '1.0.0'
            caps = getattr(mod, 'capabilities', [module_name])
            bus.register_module(module_name, version=version, capabilities=caps)

    agent.cognitive_bus = bus
    logger.info(f"CognitiveBus integrated into '{getattr(agent, 'name', 'agent')}'")
    return bus


# ─── Module-level convenience API ──────────────────────────────────

_global_bus: Optional["CognitiveBus"] = None


def get_bus(agent_name: str = "aris") -> "CognitiveBus":
    """Return the global CognitiveBus singleton, creating it if needed."""
    global _global_bus
    if _global_bus is None:
        _global_bus = CognitiveBus(agent_name=agent_name)
    return _global_bus


def route_message(user_message: str) -> dict:
    """Route a user message through the cognitive bus for evaluation.

    Returns a dict with cognitive context and routing decision.
    Uses needs-driven confidence to decide: QRE > Rules > LLM.
    """
    bus = get_bus()
    evaluation = bus.evaluate_query(user_message)
    return {
        "cognitive_context": evaluation["cognitive_context"],
        "decision": evaluation["route"],
        "confidence": evaluation["confidence"],
        "needs_triggered": evaluation["needs_triggered"],
        "response": "",
    }
