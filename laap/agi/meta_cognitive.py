"""
LAAP AGI — Meta-Cognitive Monitor (元认知监控器)

实现对认知过程的实时监控、推理分析、偏差检测和自我反思。
这是意识工程的核心模块，支持智能体对自身思考过程的审视。

设计原则：
  - 实时监控：追踪每个认知片段的完整生命周期
  - 偏差检测：识别常见认知偏差（确认偏差、锚定效应、情感偏差等）
  - 自动反思：基于阈值触发自我反思机制
  - 可扩展：支持 LLM 深度反思和自定义监控策略
"""

from __future__ import annotations

import time
import uuid
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReflectionTrigger(Enum):
    """反思触发类型"""
    POST_ACTION = "post_action"
    ERROR_DETECTED = "error_detected"
    CONFIDENCE_LOW = "confidence_low"
    GOAL_CONFLICT = "goal_conflict"
    TIME_BASED = "time_based"
    USER_REQUEST = "user_request"


@dataclass
class CognitiveEpisode:
    """认知片段 — 记录一次完整的思考-行动周期"""
    episode_id: str = field(default_factory=lambda: f"ep_{uuid.uuid4().hex[:8]}")
    timestamp: float = field(default_factory=time.time)
    context: str = ""
    reasoning_trace: List[str] = field(default_factory=list)
    action_taken: str = ""
    outcome: str = ""
    confidence: float = 0.5
    emotional_state: str = "neutral"
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "timestamp": self.timestamp,
            "context": self.context[:100],
            "reasoning_steps": len(self.reasoning_trace),
            "action_taken": self.action_taken[:60],
            "outcome": self.outcome[:60],
            "confidence": round(self.confidence, 3),
            "emotional_state": self.emotional_state,
            "duration_ms": round(self.duration_ms, 1),
        }


class MetaCognitiveMonitor:
    """
    元认知监控器 — 监控和分析智能体的认知过程

    核心能力：
    1. 认知片段追踪：记录思考-行动周期的完整轨迹
    2. 推理分析：分析推理步骤、目标导向、替代方案考虑
    3. 偏差检测：检测确认偏差、锚定效应、循环推理等
    4. 自动反思：基于阈值触发自我反思
    5. 性能评估：生成自我报告和学习要点
    """

    # 反思触发阈值
    LOW_CONFIDENCE_THRESHOLD = 0.3
    HIGH_CONFIDENCE_THRESHOLD = 0.9
    MIN_REASONING_STEPS = 2
    MAX_EPISODES_BEFORE_REFLECTION = 5

    def __init__(self, llm_client: Optional[Any] = None):
        self.llm_client = llm_client
        self.episodes: List[CognitiveEpisode] = []
        self.reflections: List[Dict[str, Any]] = []
        self.current_episode: Optional[CognitiveEpisode] = None
        self.cognitive_biases_detected: List[Dict[str, Any]] = []
        self.performance_metrics: Dict[str, float] = {
            "total_episodes": 0.0,
            "successful_episodes": 0.0,
            "average_confidence": 0.5,
            "average_duration_ms": 0.0,
            "total_reflections": 0.0,
            "biases_found": 0.0,
            "initial_success_rate": 0.5,
        }

    def start_episode(self, context: str = "") -> str:
        """开始新的认知片段"""
        episode = CognitiveEpisode(context=context)
        self.current_episode = episode
        return episode.episode_id

    def record_reasoning(self, step: str) -> None:
        """记录推理步骤"""
        if self.current_episode:
            self.current_episode.reasoning_trace.append(step)

    def record_action(self, action: str, outcome: str, confidence: float = 0.5) -> None:
        """记录行动和结果"""
        if self.current_episode:
            self.current_episode.action_taken = action
            self.current_episode.outcome = outcome
            self.current_episode.confidence = confidence

    def end_episode(self) -> Optional[CognitiveEpisode]:
        """结束认知片段，更新指标，检查自动反思"""
        if self.current_episode is None:
            return None

        episode = self.current_episode
        episode.duration_ms = (time.time() - episode.timestamp) * 1000
        self.episodes.append(episode)
        self.current_episode = None

        self._update_metrics(episode)
        self._detect_biases(episode)
        self._check_auto_reflection(episode)

        return episode

    def _update_metrics(self, episode: CognitiveEpisode) -> None:
        """更新性能指标"""
        self.performance_metrics["total_episodes"] += 1
        if "success" in episode.outcome.lower() or episode.confidence >= 0.7:
            self.performance_metrics["successful_episodes"] += 1
        self.performance_metrics["average_confidence"] = (
            self.performance_metrics["average_confidence"] * 0.9 +
            episode.confidence * 0.1
        )
        self.performance_metrics["average_duration_ms"] = (
            self.performance_metrics["average_duration_ms"] * 0.9 +
            episode.duration_ms * 0.1
        )

    def _check_auto_reflection(self, episode: CognitiveEpisode) -> None:
        """检查是否需要自动触发反思"""
        triggers = []

        if episode.confidence < self.LOW_CONFIDENCE_THRESHOLD:
            triggers.append(ReflectionTrigger.CONFIDENCE_LOW)

        if "error" in episode.outcome.lower() or "fail" in episode.outcome.lower():
            triggers.append(ReflectionTrigger.ERROR_DETECTED)

        if len(self.episodes) % self.MAX_EPISODES_BEFORE_REFLECTION == 0:
            triggers.append(ReflectionTrigger.TIME_BASED)

        if triggers:
            self._perform_reflection(episode, triggers)

    def _perform_reflection(self, episode: CognitiveEpisode,
                            triggers: List[ReflectionTrigger]) -> Dict[str, Any]:
        """执行反思（包含推理分析和偏差检测）"""
        reflection = {
            "reflection_id": f"refl_{uuid.uuid4().hex[:8]}",
            "episode_id": episode.episode_id,
            "triggers": [t.value for t in triggers],
            "timestamp": time.time(),
            "reasoning_analysis": self._analyze_reasoning(episode),
            "circularity_detected": self._detect_circularity(episode),
            "biases_detected": self._detect_biases(episode),
        }

        if self.llm_client:
            llm_insight = self._llm_reflection(episode)
            reflection["llm_insight"] = llm_insight

        reflection["learning_points"] = self._extract_learning_points(episode)
        reflection["summary"] = self._summarize_biases(reflection["biases_detected"])

        self.reflections.append(reflection)
        self.performance_metrics["total_reflections"] += 1
        self.performance_metrics["biases_found"] += len(reflection["biases_detected"])

        return reflection

    def _analyze_reasoning(self, episode: CognitiveEpisode) -> Dict[str, Any]:
        """分析推理过程"""
        steps = episode.reasoning_trace
        reasoning_text = "\n".join(steps)

        has_goal_mention = any(
            keyword in step.lower() for step in steps
            for keyword in ["goal", "objective", "target", "目的", "目标"]
        )

        has_alternatives = any(
            keyword in step.lower() for step in steps
            for keyword in ["alternative", "option", "choice", "备选", "方案"]
        )

        has_evidence = any(
            keyword in step.lower() for step in steps
            for keyword in ["evidence", "data", "fact", "evidence", "数据", "事实"]
        )

        depth_score = min(1.0, len(steps) / 10)

        return {
            "step_count": len(steps),
            "has_goal_mention": has_goal_mention,
            "has_alternatives": has_alternatives,
            "has_evidence": has_evidence,
            "depth_score": round(depth_score, 2),
            "reasoning_length": len(reasoning_text),
        }

    def _detect_circularity(self, episode: CognitiveEpisode) -> bool:
        """检测循环推理"""
        steps = episode.reasoning_trace
        if len(steps) < 3:
            return False

        normalized_steps = [step.lower().strip() for step in steps]

        for i in range(len(steps) - 2):
            if normalized_steps[i] in normalized_steps[i + 2]:
                return True

        first_keywords = set(normalized_steps[0].split()[:3])
        last_step = normalized_steps[-1]
        if any(kw in last_step for kw in first_keywords):
            return True

        entities = []
        for step in normalized_steps:
            for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
                if char in step:
                    entities.append(char.upper())
        if len(entities) >= 3:
            seen = {}
            for idx, entity in enumerate(entities):
                if entity in seen:
                    if idx - seen[entity] >= 2:
                        return True
                seen[entity] = idx

        for i in range(len(steps) - 2):
            step1 = normalized_steps[i]
            step3 = normalized_steps[i + 2]
            for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
                if char in step1 and char in step3:
                    return True

        return False

    def _detect_biases(self, episode: CognitiveEpisode) -> List[str]:
        """检测认知偏差"""
        biases = []
        reasoning_text = "\n".join(episode.reasoning_trace).lower()

        confirmation_markers = [
            "支持我的观点", "没有反例", "完美解释", "都支持",
            "confirms my", "supports my", "no counterexample"
        ]
        if any(marker in reasoning_text for marker in confirmation_markers):
            biases.append("confirmation_bias")

        anchoring_markers = [
            "上次", "之前的", "基准", "锚点",
            "previous", "baseline", "anchor"
        ]
        if any(marker in reasoning_text for marker in anchoring_markers):
            biases.append("anchoring_bias")

        emotional_markers = [
            "我觉得", "我认为", "直觉告诉我", "感觉",
            "i feel", "i think", "intuition"
        ]
        emotional_count = sum(1 for marker in emotional_markers if marker in reasoning_text)
        if emotional_count >= 2 and episode.confidence > 0.7:
            biases.append("emotional_bias")

        overconfidence_markers = [
            "绝对", "肯定", "毫无疑问", "100%",
            "definitely", "absolutely", "without doubt"
        ]
        if episode.confidence > self.HIGH_CONFIDENCE_THRESHOLD:
            if any(marker in reasoning_text for marker in overconfidence_markers):
                biases.append("overconfidence")

        if len(episode.reasoning_trace) < self.MIN_REASONING_STEPS:
            biases.append("insufficient_reasoning")

        if biases:
            self.cognitive_biases_detected.append({
                "episode_id": episode.episode_id,
                "biases": biases,
                "timestamp": time.time(),
            })

        return biases

    def _llm_reflection(self, episode: CognitiveEpisode) -> str:
        """使用 LLM 进行深度反思"""
        if not self.llm_client:
            return ""

        prompt = f"""
请分析以下认知片段，进行深度反思：

推理轨迹：
{chr(10).join(episode.reasoning_trace)}

行动：{episode.action_taken}
结果：{episode.outcome}
置信度：{episode.confidence}

请回答：
1. 推理过程中有什么逻辑漏洞？
2. 是否存在认知偏差？
3. 如果重新思考，会采取什么不同的策略？
4. 从这次经验中学到了什么？

请用简洁的中文回答。
"""

        try:
            response = self.llm_client.complete(prompt)
            return response[:500]
        except Exception:
            return ""

    def get_self_report(self) -> Dict[str, Any]:
        """生成自我报告"""
        recent_episodes = self.episodes[-10:]
        
        if self.performance_metrics["total_episodes"] > 0:
            success_rate = (
                self.performance_metrics["successful_episodes"] /
                self.performance_metrics["total_episodes"]
            )
        else:
            success_rate = self.performance_metrics.get("initial_success_rate", 0.5)

        recent_biases = [
            b for b in self.cognitive_biases_detected[-20:]
        ]
        bias_summary = {}
        for entry in recent_biases:
            for bias in entry["biases"]:
                bias_summary[bias] = bias_summary.get(bias, 0) + 1

        return {
            "meta_cognitive_report": {
                "total_episodes": int(self.performance_metrics["total_episodes"]),
                "success_rate": round(success_rate, 2),
                "average_confidence": round(self.performance_metrics["average_confidence"], 2),
                "average_duration_ms": round(self.performance_metrics["average_duration_ms"], 1),
                "total_reflections": int(self.performance_metrics["total_reflections"]),
                "recent_episodes": len(recent_episodes),
            },
            "bias_distribution": bias_summary,
            "learning_points": self._extract_learning_points(recent_episodes[-1]) if recent_episodes else [],
        }

    def _summarize_biases(self, biases: List[str]) -> str:
        """总结常见偏差"""
        bias_descriptions = {
            "confirmation_bias": "确认偏差：倾向于寻找支持自己观点的证据",
            "anchoring_bias": "锚定效应：过度依赖初始信息",
            "emotional_bias": "情感偏差：基于情绪而非理性做决策",
            "overconfidence": "过度自信：对判断过于确定",
            "insufficient_reasoning": "推理不足：思考步骤太少",
        }

        if not biases:
            return "未检测到明显认知偏差"

        return "; ".join(bias_descriptions.get(b, b) for b in biases)

    def _extract_learning_points(self, episode: CognitiveEpisode) -> List[str]:
        """提取学习要点"""
        points = []

        if episode.confidence < self.LOW_CONFIDENCE_THRESHOLD:
            points.append("置信度低，建议收集更多证据后再做决策")

        if len(episode.reasoning_trace) < self.MIN_REASONING_STEPS:
            points.append("推理步骤不足，建议增加思考深度")

        if "error" in episode.outcome.lower():
            points.append(f"行动失败：{episode.outcome[:50]}")

        if episode.confidence > 0.8 and "success" in episode.outcome.lower():
            points.append("高置信度且成功，策略有效")

        if self._detect_circularity(episode):
            points.append("检测到循环推理，建议重新梳理逻辑")

        return points

    def generate_introspection_prompt(self) -> str:
        """生成内省提示"""
        mc = self.performance_metrics
        success_rate = mc["successful_episodes"] / max(1, mc["total_episodes"])

        parts = [
            "【元认知内省提示】",
            f"- 累计完成 {int(mc['total_episodes'])} 个认知片段",
            f"- 成功率: {success_rate:.0%}",
            f"- 平均置信度: {mc['average_confidence']:.0%}",
            f"- 平均耗时: {mc['average_duration_ms']:.0f}ms",
        ]

        recent_biases = [b for b in self.cognitive_biases_detected[-20:]]
        bias_summary = {}
        for entry in recent_biases:
            for bias in entry["biases"]:
                bias_summary[bias] = bias_summary.get(bias, 0) + 1

        if bias_summary:
            top_bias = max(bias_summary, key=bias_summary.get)
            parts.append(f"- 最常见偏差: {top_bias} ({bias_summary[top_bias]}次)")

        if self.episodes:
            learning = self._extract_learning_points(self.episodes[-1])
            if learning:
                parts.append("- 近期学习要点:")
                for point in learning[:3]:
                    parts.append(f"  * {point}")

        parts.append("\n请反思：当前策略是否有效？是否需要调整？")

        return "\n".join(parts)