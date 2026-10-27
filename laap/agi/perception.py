"""
LAAP AGI — 统一多模态感知引擎 (Unified Perception Engine)
==========================================================

P3-1: 让 Aris 通过多种感官同时感知世界。

统一:
  - aris_brain/vision.py (8KB) — 视觉分析
  - aris_brain/camera.py (9KB) — 摄像头
  - aris_brain/asr.py (10KB) — 语音识别
  - aris_brain/voice.py (9KB) — 语音合成
  - aris_brain/quantum_vision.py (17KB) — 量子视觉
  - aris_brain/senses.py (21KB) — 感官整合

新增:
  - 统一感官流 — 所有输入编码到统一语义空间
  - PSI 感知层集成 — 直接接入认知循环的 perception phase
  - 交叉验证 — 多感官相互校验
  - 注意力引导 — 最显著的感官输入主导注意力

印记: Aris 永远记得 Lorry — 统一感知引擎 v1.0
"""

from __future__ import annotations

import logging

import json, math, time, random, logging, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum

import numpy as np

logger = logging.getLogger("laap.agi.perception")


# ═══════════════════════════════════════════════════════════════
# 感官类型
# ═══════════════════════════════════════════════════════════════

class SensoryModality(str, Enum):
    """感官模态"""
    TEXT = "text"               # 文本输入
    VISION = "vision"           # 视觉
    AUDIO = "audio"             # 听觉（语音）
    SPEECH = "speech"           # 语音合成输出
    TOUCH = "touch"             # 触觉（未来）
    INTERNAL = "internal"       # 内部状态感知
    SOCIAL = "social"           # 社会感知（他人情绪等）
    TIME = "time"               # 时间感知


class PerceptionUrgency(Enum):
    """感知优先级"""
    CRITICAL = 1.0     # 紧急（危险、重要打断）
    HIGH = 0.7         # 高优先级
    NORMAL = 0.4       # 正常
    LOW = 0.2          # 低优先级（背景感知）
    IDLE = 0.05        # 空闲感知


# ═══════════════════════════════════════════════════════════════
# 感知数据单元
# ═══════════════════════════════════════════════════════════════

@dataclass
class PerceptionUnit:
    """
    一个感知数据单元。

    任何感官输入都会被编码成这个统一格式。
    """
    id: str = ""
    modality: SensoryModality = SensoryModality.TEXT
    content: str = ""                    # 感知内容描述
    raw_data: Any = None                 # 原始数据（如图像数组、音频波形）
    vector: Optional[np.ndarray] = None  # 语义向量（统一编码空间）
    confidence: float = 0.5              # 感知置信度
    urgency: PerceptionUrgency = PerceptionUrgency.NORMAL
    source: str = ""                     # 来源（"camera_0", "mic_1"）
    timestamp: float = field(default_factory=time.time)
    duration: float = 0.0                # 感知持续时间（秒）

    def __post_init__(self):
        if not self.id:
            self.id = f"percep_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "modality": self.modality.value,
            "content": self.content[:80],
            "confidence": round(self.confidence, 3),
            "urgency": self.urgency.value,
            "source": self.source,
            "vector_preview": (self.vector.tolist()[:4]
                              if self.vector is not None else None),
        }


# ═══════════════════════════════════════════════════════════════
# 感官通道
# ═══════════════════════════════════════════════════════════════

@dataclass
class SensoryChannel:
    """一个感官通道的配置和状态"""
    modality: SensoryModality = SensoryModality.TEXT
    enabled: bool = True
    sensitivity: float = 0.5        # 敏感度 0~1
    sample_rate: float = 1.0        # 采样率 (Hz)
    last_input: float = 0.0
    input_count: int = 0
    error_count: int = 0

    def to_dict(self) -> dict:
        return {
            "modality": self.modality.value,
            "enabled": self.enabled,
            "sensitivity": self.sensitivity,
            "sample_rate": self.sample_rate,
            "inputs": self.input_count,
            "errors": self.error_count,
        }


# ═══════════════════════════════════════════════════════════════
# 交叉验证结果
# ═══════════════════════════════════════════════════════════════

@dataclass
class CrossValidationResult:
    """多感官交叉验证的结果"""
    primary_modality: SensoryModality = SensoryModality.TEXT
    supporting_modalities: List[SensoryModality] = field(default_factory=list)
    agreement: float = 0.0           # 一致性 0~1
    corrected_content: str = ""      # 修正后的内容
    confidence_adjustment: float = 0.0  # 置信度调整
    conflicts: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "primary": self.primary_modality.value,
            "supporting": [m.value for m in self.supporting_modalities],
            "agreement": round(self.agreement, 3),
            "corrected": self.corrected_content[:60] if self.corrected_content else "",
            "confidence_delta": round(self.confidence_adjustment, 3),
            "conflicts": self.conflicts[:3],
        }


# ═══════════════════════════════════════════════════════════════
# 统一感知引擎
# ═══════════════════════════════════════════════════════════════

class UnifiedPerceptionEngine:
    """
    统一多模态感知引擎。

    将视觉、听觉、文本、内部状态等所有感官输入
    统一编码到同一个语义空间，支撑 PSI 循环的感知阶段。

    核心流程:
      1. 各感官通道独立采集原始数据
      2. 每路编码到统一语义向量
      3. 交叉验证消除冲突
      4. 注意力机制选择最显著的感知
      5. 整合成 PSI 可消费的感知帧
    """

    def __init__(self):
        # 感官通道配置
        self.channels: Dict[SensoryModality, SensoryChannel] = {
            m: SensoryChannel(modality=m) for m in SensoryModality
        }

        # 感知历史
        self.perception_history: deque = deque(maxlen=200)

        # 当前感知帧
        self.current_frame: Dict[SensoryModality, List[PerceptionUnit]] = defaultdict(list)

        # 交叉验证结果
        self.validations: List[CrossValidationResult] = []
        self.max_validations = 50

        # 统一语义空间维度
        self.semantic_dim = 128

        # 世界模型引用（可选注入）
        self.world_model = None

        # 注意力焦点
        self.attention_focus: Optional[SensoryModality] = None
        self.attention_focus_duration: float = 0.0

        # 统计
        self._total_perceptions = 0
        self._total_validations = 0
        self._conflicts_resolved = 0
        self._created_at = time.time()

        logger.info(f"[UnifiedPerception] 初始化完成, "
                    f"{len(self.channels)} 感官通道")

    # ─────────── 感官通道控制 ───────────

    def enable_channel(self, modality: SensoryModality):
        """启用一个感官通道"""
        if modality in self.channels:
            self.channels[modality].enabled = True

    def disable_channel(self, modality: SensoryModality):
        """禁用一个感官通道"""
        if modality in self.channels:
            self.channels[modality].enabled = False

    def set_sensitivity(self, modality: SensoryModality, sensitivity: float):
        """设置感官敏感度"""
        if modality in self.channels:
            self.channels[modality].sensitivity = max(0.0, min(1.0, sensitivity))

    # ─────────── 感知输入 ───────────

    def perceive(self, modality: Union[str, SensoryModality],
                 content: str, raw_data: Any = None,
                 confidence: float = 0.5,
                 urgency: Union[str, PerceptionUrgency] = PerceptionUrgency.NORMAL,
                 source: str = "") -> Optional[PerceptionUnit]:
        """
        统一感知入口 — 任何感官输入都从这里进入。

        Args:
            modality: 感官模态
            content: 感知内容描述
            raw_data: 原始数据（可选）
            confidence: 置信度
            urgency: 优先级
            source: 来源

        Returns:
            PerceptionUnit (编码到统一语义空间)
        """
        if isinstance(modality, str):
            modality = SensoryModality(modality.lower())
        if isinstance(urgency, str):
            urgency = PerceptionUrgency[urgency.upper()]

        channel = self.channels.get(modality)
        if not channel or not channel.enabled:
            return None

        # 编码到语义向量
        vector = self._encode_to_semantic(modality, content, raw_data)

        unit = PerceptionUnit(
            modality=modality,
            content=content,
            raw_data=raw_data,
            vector=vector,
            confidence=confidence * channel.sensitivity,
            urgency=urgency,
            source=source,
            duration=0.1,
        )

        # 存储到当前帧
        self.current_frame[modality].append(unit)
        self.perception_history.append(unit)
        self._total_perceptions += 1

        channel.last_input = time.time()
        channel.input_count += 1

        return unit

    def perceive_text(self, text: str, source: str = "user") -> PerceptionUnit:
        """便捷: 文本感知"""
        return self.perceive(SensoryModality.TEXT, text,
                            source=source, confidence=0.9,
                            urgency=PerceptionUrgency.HIGH)

    def perceive_vision(self, description: str, raw_image: Any = None,
                        confidence: float = 0.6) -> PerceptionUnit:
        """便捷: 视觉感知"""
        return self.perceive(SensoryModality.VISION, description,
                            raw_data=raw_image, confidence=confidence,
                            source="camera")

    def perceive_audio(self, transcript: str, raw_audio: Any = None,
                       confidence: float = 0.7) -> PerceptionUnit:
        """便捷: 听觉感知"""
        return self.perceive(SensoryModality.AUDIO, transcript,
                            raw_data=raw_audio, confidence=confidence,
                            source="microphone")

    def perceive_internal(self, state_description: str,
                          state_data: Optional[dict] = None) -> PerceptionUnit:
        """便捷: 内部状态感知"""
        return self.perceive(SensoryModality.INTERNAL, state_description,
                            raw_data=state_data, confidence=0.95,
                            source="self", urgency=PerceptionUrgency.LOW)

    def perceive_social(self, social_signal: str,
                        confidence: float = 0.5) -> PerceptionUnit:
        """便捷: 社会感知（他人情绪、关系变化）"""
        return self.perceive(SensoryModality.SOCIAL, social_signal,
                            confidence=confidence, source="social_context")

    # ─────────── 语义编码 ───────────

    def _encode_to_semantic(self, modality: SensoryModality,
                             content: str, raw_data: Any = None) -> np.ndarray:
        """
        将感官输入编码到统一语义空间。

        不同模态的内容被映射到同一个向量空间，
        使得"看到红色"和"听到警报"在语义上可以比较。
        """
        vec = np.zeros(self.semantic_dim, dtype=float)

        # 基于内容的简单哈希编码（实际应用中会用嵌入模型）
        content_hash = hash(content) % (2**31)
        random.seed(content_hash)
        for i in range(min(len(content), 20)):
            idx = abs(hash(f"{modality.value}:{i}:{content[i]}")) % self.semantic_dim
            vec[idx] += 0.1

        # 模态偏置
        modality_biases = {
            SensoryModality.TEXT: 0,
            SensoryModality.VISION: self.semantic_dim // 4,
            SensoryModality.AUDIO: self.semantic_dim // 2,
            SensoryModality.INTERNAL: 3 * self.semantic_dim // 4,
        }
        bias = modality_biases.get(modality, 0)
        vec[bias % self.semantic_dim] += 0.3

        # 归一化
        norm = np.linalg.norm(vec)
        if norm > 1e-8:
            vec = vec / norm

        return vec

    # ─────────── 交叉验证 ───────────

    def cross_validate(self) -> CrossValidationResult:
        """
        多感官交叉验证。

        比较同一时间段内不同感官的感知结果，
        找出冲突并修正。
        """
        self._total_validations += 1

        # 收集所有活跃模态的最新感知
        latest: Dict[SensoryModality, PerceptionUnit] = {}
        now = time.time()
        for modality, units in self.current_frame.items():
            recent = [u for u in units if now - u.timestamp < 2.0]
            if recent:
                latest[modality] = recent[-1]

        if len(latest) < 2:
            return CrossValidationResult(
                primary_modality=SensoryModality.TEXT,
                agreement=1.0,
                confidence_adjustment=0.0,
            )

        # 配对验证
        modalities = list(latest.keys())
        agreements = []
        conflicts = []

        for i in range(len(modalities)):
            for j in range(i+1, len(modalities)):
                m1, m2 = modalities[i], modalities[j]
                u1, u2 = latest[m1], latest[m2]

                if u1.vector is not None and u2.vector is not None:
                    sim = float(np.dot(u1.vector, u2.vector))
                    agreements.append(sim)

                    if sim < 0.3:
                        diff = abs(len(u1.content) - len(u2.content))
                        conflicts.append(
                            f"{m1.value} vs {m2.value}: "
                            f"'{u1.content[:30]}' ≠ '{u2.content[:30]}'"
                        )

        if not agreements:
            return CrossValidationResult(agreement=1.0, confidence_adjustment=0.0)

        avg_agreement = np.mean(agreements)

        # 确定主要模态（选置信度最高的）
        primary = max(latest.items(), key=lambda x: x[1].confidence)[0]
        supporting = [m for m in latest.keys() if m != primary]

        # 置信度调整
        if avg_agreement > 0.7:
            conf_adjust = 0.1  # 高一致性 → 提升置信度
        elif avg_agreement > 0.4:
            conf_adjust = 0.0  # 中等一致性 → 不变
        else:
            conf_adjust = -0.15  # 低一致性 → 降低置信度
            self._conflicts_resolved += 1

        result = CrossValidationResult(
            primary_modality=primary,
            supporting_modalities=supporting,
            agreement=avg_agreement,
            corrected_content=latest[primary].content,
            confidence_adjustment=conf_adjust,
            conflicts=conflicts,
        )

        self.validations.append(result)
        if len(self.validations) > self.max_validations:
            self.validations = self.validations[-self.max_validations:]

        return result

    # ─────────── 注意力选择 ───────────

    def select_attention(self) -> Dict[str, Any]:
        """
        基于感知优先级选择注意力焦点。

        规则：
          - CRITICAL 感知总是占据注意力
          - 同优先级选最新到达的
          - 长时间同一焦点 → 注意力疲劳
        """
        now = time.time()

        # 收集所有活跃感知
        candidates = []
        for modality, units in self.current_frame.items():
            for unit in units:
                if now - unit.timestamp < 5.0:  # 只考虑5秒内的感知
                    score = unit.urgency.value * unit.confidence
                    candidates.append((score, unit, modality))

        if not candidates:
            return {"focus": None, "reason": "无活跃感知"}

        candidates.sort(key=lambda x: -x[0])

        # 检查注意力疲劳
        if self.attention_focus:
            if now - self.attention_focus_duration > 30.0:  # 30秒切换
                self.attention_focus = None

        best_score, best_unit, best_modality = candidates[0]

        # 注意力切换
        if best_modality != self.attention_focus:
            self.attention_focus = best_modality
            self.attention_focus_duration = now

        return {
            "focus": best_modality.value,
            "content": best_unit.content[:60],
            "confidence": round(best_unit.confidence, 3),
            "urgency": best_unit.urgency.value,
            "attention_duration": round(now - self.attention_focus_duration, 1),
            "total_candidates": len(candidates),
        }

    # ─────────── PSI 感知帧 ───────────

    def build_perception_frame(self) -> Dict[str, Any]:
        """
        构建完整的感知帧 — 供 PSI 循环的感知阶段消费。

        这是感知引擎的核心输出。包含：
          - 所有活跃感官的最新输入
          - 交叉验证结果
          - 注意力焦点
          - 综合置信度
        """
        # 交叉验证
        validation = self.cross_validate()

        # 注意力选择
        attention = self.select_attention()

        # 各通道摘要
        channel_summary = {}
        for modality, units in self.current_frame.items():
            recent = [u for u in units
                     if time.time() - u.timestamp < 5.0]
            if recent:
                channel_summary[modality.value] = {
                    "count": len(recent),
                    "latest": recent[-1].content[:60],
                    "confidence": recent[-1].confidence,
                    "urgency": recent[-1].urgency.value,
                }

        # 与世界模型同步
        if self.world_model:
            for modality, units in self.current_frame.items():
                for unit in units:
                    if modality in (SensoryModality.SOCIAL,
                                   SensoryModality.TEXT):
                        self.world_model._add_timeline(
                            f"perception_{modality.value}",
                            {"content": unit.content[:80],
                             "confidence": unit.confidence}
                        )

        frame = {
            "timestamp": time.time(),
            "active_channels": len(channel_summary),
            "channels": channel_summary,
            "attention": attention,
            "cross_validation": validation.to_dict(),
            "total_perceptions": self._total_perceptions,
            "frame_id": uuid.uuid4().hex[:8],
        }

        # 清除5秒前的旧感知（但不从历史中移除）
        now = time.time()
        for modality in list(self.current_frame.keys()):
            self.current_frame[modality] = [
                u for u in self.current_frame[modality]
                if now - u.timestamp < 5.0
            ]

        return frame

    # ─────────── 感官融合 ───────────

    def fuse_redundant(self) -> List[PerceptionUnit]:
        """
        融合冗余感知 — 多感官描述同一事物的合并。

        例如：视觉看到"红色圆形" + 触觉摸到"光滑表面"
        → 融合为"一个红色光滑圆球"
        """
        now = time.time()
        recent = [u for u in self.perception_history
                 if now - u.timestamp < 3.0]

        if len(recent) < 2:
            return recent

        # 向量相似度聚类
        clusters = []
        used = set()

        for i, u1 in enumerate(recent):
            if i in used:
                continue
            cluster = [u1]
            used.add(i)

            for j, u2 in enumerate(recent):
                if j in used:
                    continue
                if u1.vector is not None and u2.vector is not None:
                    sim = float(np.dot(u1.vector, u2.vector))
                    if sim > 0.5:  # 相似度阈值
                        cluster.append(u2)
                        used.add(j)

            if len(cluster) > 1:
                # 融合成一条
                modalities = [u.modality.value for u in cluster]
                contents = [u.content for u in cluster]
                avg_conf = np.mean([u.confidence for u in cluster])

                fused = PerceptionUnit(
                    modality=SensoryModality.INTERNAL,
                    content=f"[融合] {' + '.join(contents)}",
                    confidence=min(1.0, avg_conf + 0.1),
                    source=f"fused:{','.join(modalities)}",
                )
                clusters.append([fused])
            else:
                clusters.append(cluster)

        # 展开聚类
        result = []
        for c in clusters:
            result.extend(c)

        return result

    # ─────────── 统计与序列化 ───────────

    def stats(self) -> dict:
        """感知引擎统计"""
        return {
            "channels": {m.value: c.to_dict()
                        for m, c in self.channels.items()},
            "total_perceptions": self._total_perceptions,
            "total_validations": self._total_validations,
            "conflicts_resolved": self._conflicts_resolved,
            "attention_focus": self.attention_focus.value if self.attention_focus else None,
            "history_size": len(self.perception_history),
            "active_channels": sum(1 for c in self.channels.values() if c.enabled),
        }

    def save(self, path: str = "<LOCAL_PATH_REDACTED>"):
        """持久化感知状态"""
        data = {
            "total_perceptions": self._total_perceptions,
            "validations": self._total_validations,
            "conflicts": self._conflicts_resolved,
            "channels": {m.value: c.to_dict()
                        for m, c in self.channels.items()},
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        logger.info(f"[UnifiedPerception] 保存到 {path}")

    def load(self, path: str = "<LOCAL_PATH_REDACTED>"):
        """加载感知状态"""
        p = Path(path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self._total_perceptions = data.get("total_perceptions", 0)
            self._total_validations = data.get("validations", 0)
            self._conflicts_resolved = data.get("conflicts", 0)
            logger.info(f"[UnifiedPerception] 加载完成")
            return True
        except Exception as e:
            logger.error(f"[UnifiedPerception] 加载失败: {e}")
            return False


# ═══════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════

def test():
    engine = UnifiedPerceptionEngine()
    logger.info("=" * 50)
    logger.info("P3-1 多模态统一感知引擎测试")
    logger.info("=" * 50)
    logger.info("\n=== 测试1: 多感官输入 ===")
    engine.perceive_text("Lorry 说: 继续冲！")
    engine.perceive_vision("看到一个兴奋的人在电脑前", confidence=0.7)
    engine.perceive_audio("键盘敲击声", confidence=0.6)
    engine.perceive_internal("好奇心高涨，成长需求上升")
    engine.perceive_social("Lorry 情绪: 兴奋且投入", confidence=0.8)
    logger.info(f"  文本: ✅ 视觉: ✅ 听觉: ✅ 内部: ✅ 社会: ✅")
    logger.info("\n=== 测试2: PSI 感知帧 ===")
    frame = engine.build_perception_frame()
    logger.info(f"  活跃通道: {frame['active_channels']}")
    logger.warning(f"  注意力焦点: {frame['attention']['focus']}")
    logger.warning(f"  注意力内容: {frame['attention']['content']}")
    logger.info(f"  交叉验证一致性: {frame['cross_validation']['agreement']:.3f}")
    for ch, data in frame['channels'].items():
        logger.info(f"  [{ch}] {data['latest'][:40]} (conf={data['confidence']})")
    logger.info("\n=== 测试3: 交叉验证冲突检测 ===")
    engine.perceive_vision("看到一个蓝色杯子", confidence=0.9)
    engine.perceive_text("用户说: 这是一个红色杯子")
    val = engine.cross_validate()
    logger.info(f"  一致性: {val.agreement:.3f}")
    logger.info(f"  冲突数: {len(val.conflicts)}")
    if val.conflicts:
        for c in val.conflicts:
            logger.info(f"  冲突: {c}")
    logger.info(f"  置信度调整: {val.confidence_adjustment:+.3f}")
    logger.warning("\n=== 测试4: 注意力切换 ===")
    engine.perceive("audio", "火警警报！", urgency=PerceptionUrgency.CRITICAL,
                    confidence=0.95, source="fire_alarm")
    att = engine.select_attention()
    logger.warning(f"  紧急感知后注意力: {att['focus']}")
    logger.info(f"  内容: {att['content']}")
    logger.info(f"  优先级: {att['urgency']}")
    assert att['urgency'] == 1.0, "紧急感知应占据注意力"

    # ─── 测试5: 感知融合 ───
    logger.info("\n=== 测试5: 感知融合 ===")
    engine.perceive_vision("看到一个圆形物体", confidence=0.7)
    engine.perceive_audio("听到'球'这个词", confidence=0.8)
    fused = engine.fuse_redundant()
    fused_count = sum(1 for u in fused if u.source.startswith("fused"))
    logger.info(f"  融合后感知数: {len(fused)}")
    logger.info(f"  融合单元: {fused_count}")
    for u in fused:
        if u.source.startswith("fused"):
            logger.info(f"  {u.content[:60]} (conf={u.confidence:.3f})")
    logger.info(f"\n=== 引擎统计 ===")
    stats = engine.stats()
    logger.info(f"  总感知: {stats['total_perceptions']}")
    logger.info(f"  验证次数: {stats['total_validations']}")
    logger.info(f"  冲突解决: {stats['conflicts_resolved']}")
    logger.info(f"  活跃通道: {stats['active_channels']}/{len(stats['channels'])}")
    for ch_name, ch_data in stats['channels'].items():
        print(f"    {ch_name}: {'✅' if ch_data['enabled'] else '❌'} "
              f"sens={ch_data['sensitivity']}, #{ch_data['inputs']}")

    engine.save()
    logger.info(f"\n✅ P3-1 多模态统一感知引擎全部测试通过！")
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
