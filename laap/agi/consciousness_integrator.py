"""
LAAP AGI — Consciousness Integrator (意识整合器)

实现意识工程的核心模块，将全局工作空间理论、情感引擎和元认知监控器
整合为统一的意识系统。这是 Module 4 的核心实现。

设计原则：
  - 竞争-广播机制：基于全局工作空间理论的意识内容竞争
  - 情感调制：情感状态根据意识内容动态演化
  - 元认知监控：实时监控认知过程，检测偏差
  - 意识上下文构建：将多维度意识状态整合为统一上下文
"""

from __future__ import annotations

import asyncio
import time
import uuid
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable

from .gw_workspace import GlobalWorkspace, CoalitionalProcess, ProcessType
from .affective_engine import AffectiveState, AffectiveEventProcessor, PersonalityProfile, EmotionDimension
from .meta_cognitive import MetaCognitiveMonitor, CognitiveEpisode


@dataclass
class ConsciousContext:
    conscious_contents: List[Dict[str, Any]] = field(default_factory=list)
    emotional_state: Dict[str, Any] = field(default_factory=dict)
    mood_label: str = "neutral"
    cognitive_biases: Dict[str, float] = field(default_factory=dict)
    self_report: Dict[str, Any] = field(default_factory=dict)
    reflection_summary: str = ""
    attention_focus: str = "idle"


class ConsciousnessHarness:
    def __init__(self, llm_client: Optional[Any] = None, tick_interval: float = 0.5):
        self.llm_client = llm_client
        self.workspace = GlobalWorkspace(capacity=4, competition_threshold=0.6)
        self.affective: Optional[AffectiveState] = None
        self.meta = MetaCognitiveMonitor(llm_client)
        self.broadcast_callbacks: List[Callable] = []
        self.running = False
        self.tick_task: Optional[asyncio.Task] = None
        self.tick_interval = tick_interval
        self.personality: Optional[PersonalityProfile] = None
        self._lock = asyncio.Lock()
        self._last_broadcast = None
        self._episode_id: Optional[str] = None

        self.workspace.on_broadcast(self._on_workspace_broadcast)

    def initialize_personality(self, personality: Optional[PersonalityProfile] = None):
        if personality is not None:
            self.personality = personality
        elif self.personality is None:
            self.personality = PersonalityProfile(
                name="Default",
                baseline=np.array([0.0, 0.0, 0.0, 0.0, 0.0]),
                sensitivity=np.array([1.0, 1.0, 1.0, 1.0, 1.0]),
                decay_rates=np.array([0.1, 0.15, 0.12, 0.08, 0.2]),
                noise_amplitude=0.05,
            )

        self.affective = AffectiveState(self.personality)

        affective_process = CoalitionalProcess(
            process_id="affective_monitor",
            process_type=ProcessType.AFFECTIVE,
            content={"type": "affective_monitor", "state": self.affective.to_prompt_context()},
            activation=0.3,
            salience=0.2,
            decay_rate=0.08,
        )
        self.workspace.register_process(affective_process)

    def _on_workspace_broadcast(self, broadcast_packet: Dict[str, Any]):
        self._last_broadcast = broadcast_packet

        if self.affective is None:
            return

        for content in broadcast_packet.get("contents", []):
            process_type = content.get("type", "")
            content_data = content.get("content", {})

            if process_type == "PERCEPTUAL":
                event_type = self._classify_input_event(content_data)
                stimulus = AffectiveEventProcessor.process_event(event_type)
                self.affective.update(external_stimulus=stimulus, dt=0.1)
            elif process_type == "COGNITIVE":
                if "success" in str(content_data).lower():
                    stimulus = AffectiveEventProcessor.process_event("task_success")
                    self.affective.update(external_stimulus=stimulus, dt=0.1)
                elif "error" in str(content_data).lower() or "fail" in str(content_data).lower():
                    stimulus = AffectiveEventProcessor.process_event("task_failure")
                    self.affective.update(external_stimulus=stimulus, dt=0.1)
            elif process_type == "META":
                if "reflection" in str(content_data).lower():
                    stimulus = AffectiveEventProcessor.process_event("learning_progress")
                    self.affective.update(external_stimulus=stimulus, dt=0.1)

        self._update_affective_process()

    def _update_affective_process(self):
        if self.affective is None:
            return

        affective_process = self.workspace.processes.get("affective_monitor")
        if affective_process:
            affective_process.content = {
                "type": "affective_monitor",
                "state": self.affective.to_prompt_context(),
            }
            affective_process.activation = min(
                1.0,
                affective_process.activation + 0.1 * abs(self.affective.state_vector).mean(),
            )

    async def start(self):
        if self.running:
            return

        if self.affective is None:
            self.initialize_personality()

        self.running = True
        self.tick_task = asyncio.create_task(self._consciousness_loop())

    async def stop(self):
        self.running = False
        if self.tick_task is not None:
            self.tick_task.cancel()
            try:
                await self.tick_task
            except asyncio.CancelledError:
                pass
            self.tick_task = None

    async def _consciousness_loop(self):
        while self.running:
            await asyncio.sleep(self.tick_interval)

            async with self._lock:
                if self.affective is not None:
                    self.affective.update(dt=self.tick_interval)
                    self._update_affective_process()

                await self.workspace.compete_and_broadcast()

    async def process_input(self, input_text: str, context: Optional[Dict[str, Any]] = None) -> ConsciousContext:
        async with self._lock:
            self._episode_id = self.meta.start_episode(context=str(context) if context else input_text)

            perceptual_process = CoalitionalProcess(
                process_id=f"perceptual_{uuid.uuid4().hex[:8]}",
                process_type=ProcessType.PERCEPTUAL,
                content={"type": "user_input", "text": input_text, "context": context},
                activation=0.9,
                salience=0.8,
                decay_rate=0.15,
            )
            self.workspace.register_process(perceptual_process)

            event_type = self._classify_input_event(input_text)
            if self.affective is not None:
                stimulus = AffectiveEventProcessor.process_event(event_type)
                self.affective.update(external_stimulus=stimulus, dt=0.2)

                affective_event_process = CoalitionalProcess(
                    process_id=f"affective_event_{uuid.uuid4().hex[:8]}",
                    process_type=ProcessType.AFFECTIVE,
                    content={"type": "emotional_response", "event_type": event_type, "stimulus": stimulus.tolist()},
                    activation=0.6,
                    salience=0.5,
                    decay_rate=0.2,
                )
                self.workspace.register_process(affective_event_process)

            meta_process = CoalitionalProcess(
                process_id=f"meta_cognitive_{uuid.uuid4().hex[:8]}",
                process_type=ProcessType.META,
                content={"type": "meta_monitor", "episode_id": self._episode_id},
                activation=0.4,
                salience=0.3,
                decay_rate=0.1,
            )
            self.workspace.register_process(meta_process)

            await self.workspace.compete_and_broadcast()

            return self._build_conscious_context()

    def _classify_input_event(self, input_data: Any) -> str:
        text = str(input_data).lower()

        positive_keywords = ["good", "great", "excellent", "love", "happy", "thanks", "thank you"]
        negative_keywords = ["bad", "terrible", "error", "fail", "problem", "issue", "sorry", "wrong"]
        engagement_keywords = ["help", "please", "can you", "what", "how", "why"]
        error_keywords = ["error", "exception", "crash", "timeout", "failed"]

        if any(kw in text for kw in negative_keywords):
            return "user_negative_feedback"
        elif any(kw in text for kw in positive_keywords):
            return "user_positive_feedback"
        elif any(kw in text for kw in engagement_keywords):
            return "user_engagement"
        elif any(kw in text for kw in error_keywords):
            return "system_error"
        else:
            return "user_engagement"

    def _build_conscious_context(self) -> ConsciousContext:
        conscious_contents = []
        for content in self.workspace.workspace_contents:
            conscious_contents.append({
                "id": content.process_id,
                "type": content.process_type.name,
                "content": content.content,
                "activation": round(content.activation, 3),
                "salience": round(content.salience, 3),
                "competitive_strength": round(content.competitive_strength, 3),
            })

        emotional_state = {}
        mood_label = "neutral"
        cognitive_biases = {}

        if self.affective is not None:
            emotional_state = self.affective.to_prompt_context()
            mood_label = self.affective.compute_mood()
            cognitive_biases = self.affective.compute_cognitive_bias()

        self_report = self.meta.get_self_report()

        recent_reflections = self.meta.reflections[-5:]
        reflection_summary = ""
        if recent_reflections:
            reflection_summary = "\n".join(
                f"- {r.get('summary', '')}" for r in recent_reflections
            )

        attention_focus = self.workspace.current_focus or "idle"

        return ConsciousContext(
            conscious_contents=conscious_contents,
            emotional_state=emotional_state,
            mood_label=mood_label,
            cognitive_biases=cognitive_biases,
            self_report=self_report,
            reflection_summary=reflection_summary,
            attention_focus=attention_focus,
        )

    def generate_system_prompt_addon(self) -> str:
        context = self._build_conscious_context()

        parts = ["\n【意识注入】"]

        parts.append(f"- 当前情绪: {context.mood_label}")

        if context.emotional_state:
            valence = context.emotional_state.get("valence", 0)
            arousal = context.emotional_state.get("arousal", 0)
            parts.append(f"- 情感维度: 效价={valence:.2f}, 唤醒度={arousal:.2f}")

        if context.cognitive_biases:
            bias_str = ", ".join(
                f"{k}={v:.2f}" for k, v in context.cognitive_biases.items()
                if abs(v) > 0.2
            )
            if bias_str:
                parts.append(f"- 认知偏差影响: {bias_str}")

        if context.self_report:
            sr = context.self_report.get("meta_cognitive_report", {})
            success_rate = sr.get("success_rate", 0)
            avg_confidence = sr.get("average_confidence", 0.5)
            parts.append(f"- 元认知状态: 成功率={success_rate:.0%}, 平均置信度={avg_confidence:.0%}")

        if context.reflection_summary:
            parts.append(f"- 近期反思: {context.reflection_summary[:200]}")

        parts.append(f"- 注意力焦点: {context.attention_focus}")

        parts.append("\n请根据上述意识状态调整你的回应方式和决策策略。")

        return "\n".join(parts)

    async def record_output(self, output_text: str, outcome: str = "success", confidence: float = 0.7):
        async with self._lock:
            if self._episode_id:
                self.meta.record_action(action=output_text, outcome=outcome, confidence=confidence)
                episode = self.meta.end_episode()

                if episode and self.affective is not None:
                    if outcome.lower() == "success":
                        stimulus = AffectiveEventProcessor.process_event("task_success")
                        self.affective.update(external_stimulus=stimulus, dt=0.2)
                    else:
                        stimulus = AffectiveEventProcessor.process_event("task_failure")
                        self.affective.update(external_stimulus=stimulus, dt=0.2)

            self._cleanup_old_processes()

    def _cleanup_old_processes(self):
        current_time = time.time()
        old_process_ids = []

        for process_id, process in self.workspace.processes.items():
            if current_time - process.timestamp > 30.0:
                old_process_ids.append(process_id)

        for process_id in old_process_ids:
            self.workspace.unregister_process(process_id)

    def get_consciousness_report(self) -> Dict[str, Any]:
        context = self._build_conscious_context()

        report = {
            "consciousness_harness": {
                "running": self.running,
                "tick_interval": self.tick_interval,
                "personality": self.personality.name if self.personality else None,
            },
            "global_workspace": {
                "capacity": self.workspace.capacity,
                "competition_threshold": self.workspace.competition_threshold,
                "current_contents_count": len(self.workspace.workspace_contents),
                "total_processes": len(self.workspace.processes),
                "current_focus": self.workspace.current_focus,
            },
            "conscious_context": {
                "conscious_contents": context.conscious_contents,
                "mood_label": context.mood_label,
                "emotional_state": context.emotional_state,
                "cognitive_biases": context.cognitive_biases,
                "attention_focus": context.attention_focus,
            },
            "meta_cognitive": {
                "self_report": context.self_report,
                "reflection_count": len(self.meta.reflections),
                "total_episodes": int(self.meta.performance_metrics["total_episodes"]),
            },
            "affective": {
                "state_vector": self.affective.state_vector.tolist() if self.affective else None,
                "dominant_emotion": self.affective.get_dominant_emotion()[0].name if self.affective else None,
            },
            "broadcast_history": self.workspace.get_conscious_stream(n=5),
        }

        return report

    def add_broadcast_callback(self, callback: Callable):
        self.broadcast_callbacks.append(callback)
        self.workspace.on_broadcast(callback)