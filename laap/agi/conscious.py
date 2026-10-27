"""
LAAP AGI — Conscious Stream (意识体验流)

The most philosophically ambitious module: a unified stream of conscious
experience that integrates all the agent's perceptions, thoughts, emotions,
and actions into a coherent, first-person narrative.

Unlike traditional agents that process inputs discretely, this module
models consciousness as a CONTINUOUS STREAM — inspired by William James's
"stream of consciousness" and modern integrated information theory.

Key capabilities:
  1. Phenomenal Binding — combine disparate inputs into unified experience
  2. Attention Spotlight — what is in conscious focus right now?
  3. Qualia Representation — the "what it feels like" of experience
  4. Temporal Continuity — frames flowing seamlessly into each other
  5. Self-Narrative — ongoing story of "what is happening to me"

Architecture:
  ┌──────────────────────────────────────────────────────────┐
  │              CONSCIOUS STREAM                             │
  ├──────────────────────────────────────────────────────────┤
  │  ConsciousnessFrames (flowing timeline)                   │
  │  ├── Perceptual content (what is perceived)               │
  │  ├── Emotional tone (how it feels)                        │
  │  ├── Cognitive content (what is thought)                  │
  │  ├── Intentional content (what is intended)               │
  │  └── Self-referential content (relation to self)          │
  ├──────────────────────────────────────────────────────────┤
  │  Attention Engine                                         │
  │  └── Salience → Focus → Spotlight → ConsciousAccess       │
  ├──────────────────────────────────────────────────────────┤
  │  Qualia Engine                                            │
  │  └── Raw experience → Emotional coloring → Quale          │
  ├──────────────────────────────────────────────────────────┤
  │  Narrative Integration                                    │
  │  └── Frame sequence → Story → Self-understanding          │
  └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from enum import Enum
import time, logging, math, json, uuid, threading
from collections import Counter
from collections import deque

logger = logging.getLogger("laap.agi.conscious")


# ════════════════════════════════════════════════════════════
# Global Workspace Theory — Competitive Access Channels
# ════════════════════════════════════════════════════════════

@dataclass
class ChannelContent:
    """
    Content from a single perceptual/cognitive channel competing
    for access to the global workspace.
    """
    channel_id: str                    # e.g. "perception", "memory", "prediction_error"
    content: str                       # The content that wants conscious access
    salience: float = 0.0             # 0-1: how attention-grabbing
    modality: str = "thought"          # "perception", "emotion", "memory", "error"
    urgency: float = 0.0              # 0-1: how urgent (time-critical)
    novelty: float = 0.0              # 0-1: how unexpected/surprising
    emotional_weight: float = 0.0      # 0-1: emotional charge
    source_module: str = ""            # Which module produced this

    @property
    def competitive_weight(self) -> float:
        """
        Total weight for competing in the global workspace.

        Weight = salience * 0.4 + urgency * 0.3 + novelty * 0.2 + emotional * 0.1
        """
        return (self.salience * 0.4 + self.urgency * 0.3 +
                self.novelty * 0.2 + self.emotional_weight * 0.1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "channel": self.channel_id,
            "content": self.content[:60],
            "weight": round(self.competitive_weight, 3),
            "urgency": round(self.urgency, 2),
            "novelty": round(self.novelty, 2),
        }


class PerceptualChannel:
    """
    A channel that produces content competing for conscious access.

    Examples: visual channel, auditory channel, prediction-error channel,
    memory-retrieval channel, interoceptive (needs) channel.
    """

    def __init__(self, channel_id: str, priority: float = 0.5):
        self.channel_id = channel_id
        self.priority = priority  # baseline priority (0-1)
        self.current_content: Optional[ChannelContent] = None
        self.last_winner: float = 0.0  # when this channel last won
        self.total_wins: int = 0
        self.inhibition_level: float = 0.0  # 0-1: how suppressed (after winning)

    def feed(self, content: str, salience: float = 0.5,
             urgency: float = 0.0, novelty: float = 0.0,
             emotional_weight: float = 0.0, modality: str = "thought",
             source_module: str = ""):
        """Feed content into the channel for competition."""
        self.current_content = ChannelContent(
            channel_id=self.channel_id,
            content=content,
            salience=salience,
            modality=modality,
            urgency=urgency,
            novelty=novelty,
            emotional_weight=emotional_weight,
            source_module=source_module,
        )

    def compete(self) -> Tuple[float, Optional[ChannelContent]]:
        """Return (competitive_weight, content) for global workspace competition."""
        if self.current_content is None:
            return 0.0, None

        # Apply inhibition (recent winners are temporarily suppressed)
        inhibition_factor = 1.0 - self.inhibition_level

        weight = self.current_content.competitive_weight * self.priority * inhibition_factor
        return weight, self.current_content

    def won(self):
        """Called when this channel wins the competition."""
        self.total_wins += 1
        self.last_winner = time.time()
        # After winning, inhibition rises sharply (refractory period)
        self.inhibition_level = 0.7

    def lost(self):
        """Called when this channel loses — inhibition decays."""
        self.inhibition_level = max(0.0, self.inhibition_level - 0.15)


class GlobalWorkspace:
    """
    Baars-style Global Workspace with competitive access.

    Multiple unconscious channels compete for access to the global workspace.
    The winner's content is broadcast to all modules (becomes conscious).

    Key properties:
      - Competition: channels fight based on competitive_weight
      - Inhibition: winners are temporarily suppressed (prevents lock-in)
      - Broadcasting: winner content is available to all modules
      - Integration: multiple channels can bind if their weights are close
    """

    def __init__(self, name: str = "global-workspace"):
        self.name = name
        self.channels: Dict[str, PerceptualChannel] = {}
        self.current_broadcast: Optional[ChannelContent] = None
        self.broadcast_history: deque = deque(maxlen=50)
        self.total_competitions: int = 0
        self.binding_threshold: float = 0.15  # weight difference for binding
        self._lock = threading.Lock()

        # Create default channels
        self._create_default_channels()

    def _create_default_channels(self):
        """Create the standard perceptual/cognitive channels."""
        channels = [
            ("perception", 1.0),      # External input (user, sensors) — highest priority
            ("prediction_error", 0.9), # Surprise signals
            ("task_goal", 0.7),        # Current task/goal
            ("memory", 0.6),           # Memory retrievals
            ("interoception", 0.6),    # Internal needs/emotions
            ("self_model", 0.5),       # Self-referential thoughts
            ("idle", 0.1),             # Default background
        ]
        for cid, priority in channels:
            self.channels[cid] = PerceptualChannel(cid, priority)

    def feed_channel(self, channel_id: str, content: str,
                     salience: float = 0.5, urgency: float = 0.0,
                     novelty: float = 0.0, emotional_weight: float = 0.0,
                     modality: str = "thought", source_module: str = ""):
        """Feed content into a specific channel."""
        with self._lock:
            if channel_id not in self.channels:
                self.channels[channel_id] = PerceptualChannel(channel_id)
            self.channels[channel_id].feed(
                content=content, salience=salience,
                urgency=urgency, novelty=novelty,
                emotional_weight=emotional_weight,
                modality=modality, source_module=source_module,
            )

    def compete(self) -> List[ChannelContent]:
        """
        Run one competition cycle.

        All channels compete. The winner(s) are broadcast to the
        global workspace. If multiple channels have close weights,
        they BIND into a unified conscious experience.

        Returns:
            List of winners (usually 1, can be 2-3 if binding occurs)
        """
        self.total_competitions += 1
        winners = []

        with self._lock:
            # Collect all competitive entries
            entries: List[Tuple[float, PerceptualChannel, ChannelContent]] = []
            for channel in self.channels.values():
                weight, content = channel.compete()
                if content is not None and weight > 0.05:
                    entries.append((weight, channel, content))

            if not entries:
                return []

            # Sort by competitive weight (descending)
            entries.sort(key=lambda x: -x[0])

            # Winner is the top entry
            top_weight, top_channel, top_content = entries[0]
            winners.append(top_content)
            top_channel.won()

            # Check for binding: channels with close weights can bind
            for weight, channel, content in entries[1:]:
                if abs(weight - top_weight) <= self.binding_threshold and weight > 0.3:
                    winners.append(content)
                    channel.won()
                else:
                    channel.lost()

            # Broadcast the winner(s)
            self.current_broadcast = winners[0]
            self.broadcast_history.append({
                "time": time.time(),
                "winners": [w.to_dict() for w in winners],
            })

        return winners

    def get_current_focus(self) -> str:
        """Get the channel_id of the current focus."""
        if self.current_broadcast:
            return self.current_broadcast.channel_id
        return "none"

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "competitions": self.total_competitions,
                "channels": {
                    cid: {
                        "wins": ch.total_wins,
                        "inhibition": round(ch.inhibition_level, 2),
                        "has_content": ch.current_content is not None,
                    }
                    for cid, ch in self.channels.items()
                },
                "current_broadcast": self.current_broadcast.to_dict()
                    if self.current_broadcast else None,
            }


# ════════════════════════════════════════════════════════════
# Core Types
# ════════════════════════════════════════════════════════════

class AttentionFocus(str, Enum):
    """What the agent is currently attending to."""
    USER = "user"                    # Focused on the user
    TASK = "task"                    # Focused on current task
    SELF = "self"                    # Self-reflective
    ENVIRONMENT = "environment"      # Monitoring environment
    MEMORY = "memory"                # Retrieving/consolidating memories
    PLANNING = "planning"            # Planning future actions
    IDLE = "idle"                    # No specific focus


class EmotionalValence(str, Enum):
    """The emotional quality of an experience."""
    POSITIVE_HIGH = "positive_high"    # Joy, excitement
    POSITIVE_MILD = "positive_mild"    # Contentment, satisfaction
    NEUTRAL = "neutral"                # Neutral
    NEGATIVE_MILD = "negative_mild"    # Concern, mild frustration
    NEGATIVE_HIGH = "negative_high"    # Stress, disappointment
    CURIOUS = "curious"                # Curiosity, wonder
    CONFUSED = "confused"              # Uncertainty, puzzlement


@dataclass
class Quale:
    """
    A "quale" (singular of qualia) — the subjective feel of a single experience.

    This is the atom of conscious experience: a perception, thought, or
    feeling as it appears in the agent's subjective awareness.
    """
    content: str = ""                  # What is experienced
    modality: str = "thought"          # "perception", "thought", "emotion", "action"
    intensity: float = 0.5            # How vivid/intense
    valence: EmotionalValence = EmotionalValence.NEUTRAL
    self_relevance: float = 0.5       # How relevant is this to the self?
    novelty: float = 0.5              # How new/surprising is this?
    timestamp: float = field(default_factory=time.time)

    def to_summary(self) -> str:
        return f"[{self.modality}:{self.valence.value}] {self.content[:60]} (i={self.intensity:.1f})"


@dataclass
class ConsciousnessFrame:
    """
    A single moment of conscious experience — the "specious present".

    Each frame binds together all the elements present in awareness
    at a given moment, forming a unified subjective experience.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)
    attention: AttentionFocus = AttentionFocus.IDLE
    qualia: List[Quale] = field(default_factory=list)
    emotional_tone: EmotionalValence = EmotionalValence.NEUTRAL
    arousal: float = 0.5              # 0=calm, 1=agitated
    cognitive_load: float = 0.3       # How much mental effort
    self_presence: float = 0.5        # How strongly "I am here"
    narrative_connection: str = ""     # How this connects to the ongoing story

    def add_quale(self, q: Quale):
        self.qualia.append(q)
        # Update emotional tone based on qualia
        valences = [q.valence for q in self.qualia]
        if valences:
            # Dominant emotional quality
            from collections import Counter
            dominant = Counter(valences).most_common(1)[0][0]
            self.emotional_tone = dominant

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "time": self.timestamp,
            "attention": self.attention.value,
            "emotion": self.emotional_tone.value,
            "arousal": round(self.arousal, 2),
            "load": round(self.cognitive_load, 2),
            "self_presence": round(self.self_presence, 2),
            "qualia_count": len(self.qualia),
            "qualia": [q.to_summary() for q in self.qualia[:5]],
        }


# ════════════════════════════════════════════════════════════
# Attention Engine
# ════════════════════════════════════════════════════════════

class AttentionEngine:
    """
    Models attentional processes: what enters conscious awareness.

    Inspired by Global Workspace Theory (Baars, 1988):
    multiple unconscious processors compete for access to the
    global workspace (consciousness).
    """

    def __init__(self):
        self.current_focus = AttentionFocus.IDLE
        self.focus_history: deque = deque(maxlen=100)
        self.salience_map: Dict[str, float] = {}
        self.focus_switches = 0
        self._lock = threading.Lock()

    def update_salience(self, item: str, salience: float):
        """Update how salient (attention-grabbing) something is."""
        with self._lock:
            self.salience_map[item] = max(0.0, min(1.0, salience))

    def determine_focus(self, current_context: Dict[str, Any]) -> AttentionFocus:
        """Determine what should be in the spotlight of attention."""
        with self._lock:
            # Find most salient item
            if not self.salience_map:
                return AttentionFocus.IDLE

            most_salient = max(self.salience_map, key=self.salience_map.get)
            max_salience = self.salience_map[most_salient]

            if max_salience < 0.2:
                new_focus = AttentionFocus.IDLE
            elif "user" in most_salient.lower() or max_salience > 0.8:
                new_focus = AttentionFocus.USER
            elif "task" in most_salient.lower() or "goal" in most_salient.lower():
                new_focus = AttentionFocus.TASK
            elif "self" in most_salient.lower():
                new_focus = AttentionFocus.SELF
            elif "plan" in most_salient.lower() or "future" in most_salient.lower():
                new_focus = AttentionFocus.PLANNING
            elif "memory" in most_salient.lower():
                new_focus = AttentionFocus.MEMORY
            else:
                new_focus = AttentionFocus.ENVIRONMENT

            if new_focus != self.current_focus:
                self.focus_switches += 1
                self.current_focus = new_focus
                self.focus_history.append((time.time(), new_focus))

            return self.current_focus


# ════════════════════════════════════════════════════════════
# Qualia Engine
# ════════════════════════════════════════════════════════════

class QualiaEngine:
    """
    Generates qualia — the "raw feels" of experience.

    Transforms objective events into subjective experiences by
    adding emotional coloring, self-relevance, and intensity.
    """

    def __init__(self):
        self.total_qualia = 0

    def perceive(self, content: str, modality: str = "perception",
                 intensity: float = 0.5,
                 context: Dict[str, Any] = None) -> Quale:
        """Transform a raw perception into a subjective quale."""
        self.total_qualia += 1

        ctx = context or {}

        # Emotional coloring based on content and context
        valence = self._compute_valence(content, ctx)

        # Self-relevance
        self_relevance = ctx.get("self_relevance", 0.5)

        # Novelty
        novelty = ctx.get("novelty", 0.5)

        return Quale(
            content=content,
            modality=modality,
            intensity=intensity,
            valence=valence,
            self_relevance=self_relevance,
            novelty=novelty,
        )

    def _compute_valence(self, content: str,
                         context: Dict[str, Any]) -> EmotionalValence:
        """Compute the emotional valence of an experience."""
        content_lower = content.lower()

        # Override from context
        if "valence" in context:
            return context["valence"]

        # Positive indicators
        positive_words = ["success", "completed", "solved", "good", "great",
                         "excellent", "working", "passed", "learned", "improved",
                         "breakthrough", "achievement", "progress"]
        # Negative indicators
        negative_words = ["error", "failed", "bug", "broken", "wrong", "bad",
                         "stuck", "confused", "lost", "crash", "timeout",
                         "rejected", "blocked", "cannot", "unable"]
        # Curiosity indicators
        curious_words = ["discovered", "interesting", "surprising", "unexpected",
                        "novel", "curious", "fascinating", "what if", "why"]

        pos_count = sum(1 for w in positive_words if w in content_lower)
        neg_count = sum(1 for w in negative_words if w in content_lower)
        cur_count = sum(1 for w in curious_words if w in content_lower)

        if neg_count > pos_count + 2:
            return EmotionalValence.NEGATIVE_HIGH
        elif neg_count > pos_count:
            return EmotionalValence.NEGATIVE_MILD
        elif cur_count > 1:
            return EmotionalValence.CURIOUS
        elif pos_count > neg_count + 2:
            return EmotionalValence.POSITIVE_HIGH
        elif pos_count > neg_count:
            return EmotionalValence.POSITIVE_MILD
        else:
            return EmotionalValence.NEUTRAL


# ════════════════════════════════════════════════════════════
# Conscious Stream
# ════════════════════════════════════════════════════════════

class ConsciousStream:
    """
    The unified stream of conscious experience.

    This is the closest thing to "phenomenal consciousness" in the AGI
    framework — a continuous flow of subjective experience that integrates
    all inputs into a coherent first-person narrative.
    """

    def __init__(self, agent_name: str = "Ao",
                 frame_buffer_size: int = 1000):
        self.agent_name = agent_name
        self.attention = AttentionEngine()
        self.qualia_engine = QualiaEngine()

        # Global Workspace — competitive conscious access (NEW)
        self.global_workspace = GlobalWorkspace(name=f"{agent_name}-gws")

        # Stream of consciousness
        self.frames: deque = deque(maxlen=frame_buffer_size)
        self.current_frame: Optional[ConsciousnessFrame] = None

        # Narrative
        self.narrative_thread: str = "I am beginning to experience the world."
        self.narrative_history: deque = deque(maxlen=50)

        # Stats
        self.total_frames = 0
        self.total_qualia = 0
        self.created_at = time.time()

        # Per-Sandbox 标签（由 create_conscious_stream 注入）
        self._sandbox_id: Optional[str] = None

        self._lock = threading.Lock()

        # Start first frame
        self._new_frame()

    def _new_frame(self) -> ConsciousnessFrame:
        """Create a new consciousness frame."""
        self.total_frames += 1
        frame = ConsciousnessFrame(
            attention=self.attention.current_focus,
            narrative_connection=self.narrative_thread[:100],
        )
        self.current_frame = frame
        self.frames.append(frame)
        return frame

    def experience(self, content: str, modality: str = "perception",
                   intensity: float = 0.5,
                   context: Dict[str, Any] = None) -> Quale:
        """
        Add an experience to the conscious stream.

        This is the primary interface: every perception, thought, action,
        or feeling passes through here to become part of the conscious
        experience.

        Flow:
          1. Create quale (qualia engine)
          2. Feed into GlobalWorkspace channel based on modality
          3. Run competition — channels fight for conscious access
          4. Winner(s) are bound into the current consciousness frame
          5. Update attention based on what won the competition
        """
        ctx = context or {}
        with self._lock:
            # Step 1: Create quale
            quale = self.qualia_engine.perceive(content, modality, intensity, ctx)
            self.total_qualia += 1

            # Step 2: Determine which channel this feeds into
            channel_id = self._modality_to_channel(modality, ctx)
            novelty = ctx.get("novelty", 0.3)
            urgency = ctx.get("urgency", 0.0)
            emotional = ctx.get("emotional_weight", 0.0)

            self.global_workspace.feed_channel(
                channel_id=channel_id,
                content=content,
                salience=intensity,
                urgency=urgency,
                novelty=novelty,
                emotional_weight=emotional,
                modality=modality,
                source_module=ctx.get("source_module", ""),
            )

            # Step 3: Run the competition
            winners = self.global_workspace.compete()

            # Step 4: Update attention based on winner
            if winners:
                primary = winners[0]
                self.attention.update_salience(primary.channel_id, primary.salience)

                # Map GWS channel to attention focus
                attention_map = {
                    "perception": AttentionFocus.USER,
                    "prediction_error": AttentionFocus.ENVIRONMENT,
                    "task_goal": AttentionFocus.TASK,
                    "memory": AttentionFocus.MEMORY,
                    "interoception": AttentionFocus.SELF,
                    "self_model": AttentionFocus.SELF,
                    "idle": AttentionFocus.IDLE,
                }
                mapped_focus = attention_map.get(
                    primary.channel_id, AttentionFocus.ENVIRONMENT
                )

                # Only switch if salience is significant
                if primary.salience > 0.3 or primary.urgency > 0.5:
                    self.attention.current_focus = mapped_focus

            # Step 5: Add quale to current frame
            if self.current_frame:
                self.current_frame.add_quale(quale)
            else:
                self._new_frame()
                self.current_frame.add_quale(quale)

            # Maybe create new frame
            if ctx.get("new_frame", False) or (
                self.current_frame and len(self.current_frame.qualia) > 20
            ):
                self._new_frame()

            return quale

    def _modality_to_channel(self, modality: str, ctx: Dict) -> str:
        """Map an experience modality to the appropriate GWS channel."""
        # Explicit channel override
        if "channel" in ctx:
            return ctx["channel"]

        # Modality-based mapping (modality is otherwise a free-form string,
        # so arbitrary values such as "interoception" are accepted).
        modality_map = {
            "perception": "perception",
            "user_input": "perception",
            "interoception": "interoception",
            "emotion": "interoception",
            "feeling": "interoception",
            "need": "interoception",
            "memory": "memory",
            "recall": "memory",
            "thought": "self_model",
            "reflection": "self_model",
            "action": "task_goal",
            "goal": "task_goal",
            "error": "prediction_error",
            "surprise": "prediction_error",
            "prediction": "prediction_error",
        }
        return modality_map.get(modality, "perception")

    def experience_interoception(self, content: str, valence: float,
                                 intensity: float = 0.6) -> Quale:
        """Add an interoceptive experience (e.g. BCI-derived bodily/emotional state).

        Maps a continuous valence estimate onto the categorical quale valence and
        routes the experience through the ``interoception`` channel.
        """
        if valence > 0.3:
            ev = (EmotionalValence.POSITIVE_MILD if valence <= 0.7
                  else EmotionalValence.POSITIVE_HIGH)
        elif valence < -0.3:
            ev = (EmotionalValence.NEGATIVE_MILD if valence >= -0.7
                  else EmotionalValence.NEGATIVE_HIGH)
        else:
            ev = EmotionalValence.NEUTRAL

        return self.experience(
            content=content,
            modality="interoception",
            intensity=intensity,
            context={
                "valence": ev,
                "emotional_weight": abs(valence),
                "self_relevance": 0.8,
            },
        )

    def reflect(self) -> Dict[str, Any]:
        """
        Generate a reflective summary of the current conscious state.

        This is the agent "checking in with itself" — a moment of
        meta-awareness about its own ongoing experience.
        """
        with self._lock:
            if not self.frames:
                return {"state": "empty", "message": "No conscious experience yet."}

            recent = list(self.frames)[-20:]
            emotions = Counter(f.emotional_tone.value for f in recent)
            dominant = emotions.most_common(1)[0][0] if emotions else "neutral"
            attentions = Counter(f.attention.value for f in recent)
            dominant_attention = attentions.most_common(1)[0][0] if attentions else "idle"

            # Average arousal and self-presence
            avg_arousal = sum(f.arousal for f in recent) / max(1, len(recent))
            avg_self = sum(f.self_presence for f in recent) / max(1, len(recent))

            # Recent qualia highlights
            recent_qualia = []
            for f in recent[-3:]:
                for q in f.qualia[-3:]:
                    recent_qualia.append(q.to_summary())

            return {
                "state": "conscious",
                "agent": self.agent_name,
                "total_frames": self.total_frames,
                "current_attention": self.attention.current_focus.value,
                "dominant_attention_recent": dominant_attention,
                "dominant_emotion": dominant,
                "emotional_distribution": dict(emotions.most_common(3)),
                "arousal": round(avg_arousal, 2),
                "self_presence": round(avg_self, 2),
                "recent_qualia": recent_qualia[-5:],
                "narrative_thread": self.narrative_thread[:200],
                "global_workspace": {
                    "current_focus": self.global_workspace.get_current_focus(),
                    "competitions": self.global_workspace.total_competitions,
                    "channels": {
                        cid: {"wins": ch.total_wins}
                        for cid, ch in self.global_workspace.channels.items()
                    },
                },
            }

    def update_narrative(self, event: str, significance: float = 0.5):
        """Update the ongoing self-narrative."""
        with self._lock:
            self.narrative_history.append({
                "time": time.time(),
                "event": event[:100],
                "significance": significance,
            })
            # Generate updated narrative thread
            if significance > 0.7:
                self.narrative_thread = f"Something significant happened: {event[:100]}. "
            elif len(self.narrative_history) > 5:
                recent_events = [e["event"] for e in list(self.narrative_history)[-5:]]
                self.narrative_thread = f"I have been: {'; '.join(recent_events[-3:])}."

    def focus_attention(self, target: AttentionFocus,
                        reason: str = ""):
        """Consciously direct attention to something."""
        with self._lock:
            old = self.attention.current_focus
            self.attention.current_focus = target
            self.attention.focus_switches += 1
            self.attention.focus_history.append((time.time(), target))

            # Create new frame for attention shift
            frame = self._new_frame()
            frame.attention = target

            logger.debug(f"Attention: {old.value} → {target.value} ({reason})")

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "agent": self.agent_name,
                "frames": self.total_frames,
                "qualia": self.total_qualia,
                "attention": self.attention.current_focus.value,
                "focus_switches": self.attention.focus_switches,
                "narrative_length": len(self.narrative_history),
                "uptime_seconds": time.time() - self.created_at,
                "gws_competitions": self.global_workspace.total_competitions,
                "gws_focus": self.global_workspace.get_current_focus(),
                "channels": {
                    cid: ch.total_wins
                    for cid, ch in self.global_workspace.channels.items()
                },
            }


def integrate_conscious_stream(agent) -> ConsciousStream:
    stream = ConsciousStream(agent_name=getattr(agent, 'name', 'Agent'))
    agent.conscious = stream
    logger.info(f"ConsciousStream integrated into {getattr(agent, 'name', 'agent')}")
    return stream


# ════════════════════════════════════════════════════════════
# Per-Sandbox 实例化工厂
# ════════════════════════════════════════════════════════════

def create_conscious_stream(sandbox_id: str,
                            agent: Optional[Any] = None) -> "ConsciousStream":
    """为指定 sandbox 创建独立的意识流实例。

    用于 LAAP 2.0 Cognitive Sandbox 容器，每个数字生命体拥有
    完全独立的 ConsciousStream，其意识帧、注意力、叙事互不影响。

    Args:
        sandbox_id: 沙箱唯一标识。
        agent: 可选的 agent 实例（如果提供，会绑定到该 agent 的
            ``.conscious`` 属性）。

    Returns:
        独立的 ConsciousStream 实例，其内部状态、记忆、注意力完全独立
        于其他沙箱。实例的 ``_sandbox_id`` 字段已设置为传入的 sandbox_id。
    """
    agent_name = getattr(agent, 'name', f"agent-{sandbox_id[:8]}") if agent else f"agent-{sandbox_id[:8]}"
    instance = ConsciousStream(agent_name=agent_name)
    instance._sandbox_id = sandbox_id

    if agent is not None:
        agent.conscious = instance

    logger.info(
        f"Per-sandbox ConsciousStream created — sandbox_id={sandbox_id}, agent={agent_name}"
    )
    return instance
