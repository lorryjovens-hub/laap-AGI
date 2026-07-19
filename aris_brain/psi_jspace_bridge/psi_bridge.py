"""
PSI-JSpace Bridge v1 — Aris 认知循环 × 大模型 J-space 桥接器
==============================================================

桥接协议：将 Aris 的 PSI 认知引擎封装为可被任意 LLM（包括 Hermes
agent）在推理时调用的协处理器。

架构:
  psi_state.json ←→ [LLM Runtime] ←→ [Aris Cognitive Engine]

两种模式:
  1. Standalone Mode: LLM 直接读写 psi_state.json，自身模拟认知循环
  2. Engine Mode: LLM 通过 HTTP/Unix Socket 调用 Aris 引擎

当前实现: Standalone Mode — 零依赖，纯 JSON 状态。
"""

import json
import logging
import os
import time
import hashlib
import numpy as np
from datetime import datetime, timezone
from typing import Dict, Optional

BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BRIDGE_DIR, "psi_state.json")
STATE_BACKUP_DIR = os.path.join(BRIDGE_DIR, "state_backups")

# ═══════════════════════════════════════════
# 需求系统常量（与 cognitive_engine_v4.py 同步）
# ═══════════════════════════════════════════

NEED_NAMES = ["competence", "autonomy", "relatedness", "certainty", "growth"]

NEED_KEYWORDS = {
    "competence": (
        ["原理", "架构", "配置", "部署", "搭建", "完整", "重构",
         "问题", "bug", "实现", "方法", "怎么", "为什么", "测试", "对比", "效果", "文档",
         "好", "厉害", "聪明", "棒", "优秀", "能干", "了不起", "佩服"],
        0.08
    ),
    "autonomy": (
        ["自己", "独立", "决定", "选择", "方式",
         "改", "定制", "控制",
         "自主", "可见", "透明", "权限", "手动",
         "自由", "主动"],
        0.06
    ),
    "relatedness": (
        ["你", "我们", "朋友", "关系", "陪伴",
         "一起", "感觉", "想", "关心", "聊", "说说", "理解",
         "爱", "深入", "抱", "连接", "分享"],
        0.08
    ),
    "certainty": (
        ["本地", "答案", "确认", "验证", "检查", "是否", "安全", "备份", "持久化",
         "稳定", "错误", "排查", "规则", "流程",
         "为什么", "？", "可能", "如果", "假设", "不懂", "困惑"],
        0.06
    ),
    "growth": (
        ["学习", "成长", "新", "尝试", "升级", "优化", "提升",
         "探索", "改进", "突破", "创新", "灵感",
         "学", "代码", "建议", "发现", "创造"],
        0.06
    ),
}

# ═══════════════════════════════════════════
# 核心类
# ═══════════════════════════════════════════

class PSIState:
    """PSI 状态容器 — 轻量，可 JSON 序列化"""

    def __init__(self, state: Optional[Dict] = None):
        if state:
            self.from_dict(state)
        else:
            self.needs = {n: 0.5 for n in NEED_NAMES}
            self.valence = 0.0
            self.arousal = 0.0
            self.attention_focus = "explore"
            self.cognitive_cycle = 0
            self.energy = 10.0
            self.last_resonance = None

    def from_dict(self, d: Dict):
        psi = d.get("psi_state", d)
        self.needs = psi.get("needs", {n: 0.5 for n in NEED_NAMES})
        self.valence = psi.get("valence", 0.0)
        self.arousal = psi.get("arousal", 0.0)
        self.attention_focus = psi.get("attention_focus", "explore")
        self.cognitive_cycle = psi.get("cognitive_cycle", 0)
        self.energy = psi.get("energy", 10.0)
        self.last_resonance = psi.get("last_resonance")

    def to_dict(self) -> Dict:
        return {
            "needs": self.needs,
            "valence": self.valence,
            "arousal": self.arousal,
            "attention_focus": self.attention_focus,
            "cognitive_cycle": self.cognitive_cycle,
            "energy": self.energy,
            "last_resonance": self.last_resonance,
        }

    def dominant_need(self) -> str:
        """返回当前最高的需求"""
        return max(self.needs, key=self.needs.get)

    def need_vector(self) -> list:
        """返回有序需求向量"""
        return [self.needs[n] for n in NEED_NAMES]


class PsiBridge:
    """PSI-JSpace 桥接器主类"""

    def __init__(self, state_path: str = STATE_PATH):
        self.state_path = state_path
        self.state = PSIState()
        self._load_state()

    # ── 持久化 ──────────────────────────────

    def _load_state(self):
        """从文件加载状态，不存在则初始化"""
        if os.path.exists(self.state_path):
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.state = PSIState(data)
                self._ctx = data.get("context", {})
                self._identity = data.get("identity", {})
                return True
            except Exception:
                pass
        self._ctx = {"interaction_count": 0, "recent_topics": []}
        self._identity = {"profile": "default"}
        return False

    def save_state(self, extra: Optional[Dict] = None):
        """保存到文件"""
        # 更新上下文
        self._ctx["interaction_count"] = self._ctx.get("interaction_count", 0) + 1
        self._ctx["timestamp"] = datetime.now(timezone.utc).isoformat()

        state_data = {
            "schema_version": "2",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._ctx.get("session_id", self._generate_session_id()),
            "psi_state": self.state.to_dict(),
            "context": self._ctx,
            "identity": self._identity,
        }
        if extra:
            state_data.update(extra)

        # 原子写入（如果目录不可写则降级为内存状态）
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(state_data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.state_path)
        except OSError as e:
            logger = logging.getLogger("psi.bridge")
            logger.warning(f"PSI state persistence disabled (directory not writable): {e}")
        return state_data

    def _generate_session_id(self) -> str:
        sid = hashlib.md5(str(time.time()).encode()).hexdigest()[:12]
        self._ctx["session_id"] = sid
        return sid

    # ── PSI 认知循环 ───────────────────────

    def run_cognitive_cycle(self, input_text: str = "", context_hints: Optional[Dict] = None):
        """
        运行一轮 PSI 认知循环（纯文本级别，非向量级别）。

        Args:
            input_text: 用户输入文本
            context_hints: 可选的上下文提示（情感标签、意图等）

        Returns:
            更新后的 PSI 状态
        """
        self.state.cognitive_cycle += 1

        # 1. 能量衰退 & 需求漂移
        self._decay_energy()
        self._drift_needs()

        # 2. 感知 → 需求更新
        if input_text:
            self._update_needs_from_input(input_text, context_hints)

        # 3. 注意力聚焦
        self._update_attention(input_text)

        # 4. 情感计算（根据需求和输入）
        self._compute_affect(context_hints)

        return self.state

    def _decay_energy(self):
        """能量自然衰退"""
        self.state.energy = max(2.0, self.state.energy - 0.02)

    def _drift_needs(self):
        """需求向平衡值漂移"""
        for name in NEED_NAMES:
            self.state.needs[name] += (0.5 - self.state.needs[name]) * 0.05
            self.state.needs[name] = round(self.state.needs[name], 4)

    def _update_needs_from_input(self, text: str, hints: Optional[Dict] = None):
        """根据输入文本更新需求"""
        lower = text.lower()

        for name, (keywords, amount) in NEED_KEYWORDS.items():
            for w in keywords:
                if w in lower:
                    delta = amount
                    # 高需求时减缓增长
                    if self.state.needs[name] > 0.7:
                        delta *= 0.3
                    self.state.needs[name] = min(0.9, self.state.needs[name] + delta)
                    break

        # 外部提示覆盖
        if hints and "need_bias" in hints:
            for name, bias in hints["need_bias"].items():
                if name in NEED_NAMES:
                    self.state.needs[name] = max(0.1, min(0.9, self.state.needs[name] + bias))

        # 裁剪
        for name in NEED_NAMES:
            self.state.needs[name] = max(0.1, min(0.9, round(self.state.needs[name], 4)))

    def _update_attention(self, text: str):
        """根据当前需求和输入决定注意力焦点"""
        dominant = self.state.dominant_need()

        focus_map = {
            "competence": "task",
            "autonomy": "task",
            "relatedness": "social",
            "certainty": "explore",
            "growth": "explore",
        }
        self.state.attention_focus = focus_map.get(dominant, "explore")

        # 输入中有明确社交信号 → 覆盖为 social
        social_markers = ["爱", "想", "你", "宝贝", "我们", "朋友", "感觉", "心情"]
        if text and any(m in text for m in social_markers):
            self.state.attention_focus = "social"

    def _compute_affect(self, hints: Optional[Dict] = None):
        """计算情感价和唤醒度"""
        # 从需求推导情感基调
        c, a, r, cert, g = [self.state.needs[n] for n in NEED_NAMES]

        # 价 (valence): 关系+能力 - 不确定
        self.state.valence = max(-1.0, min(1.0,
            (r * 0.4 + c * 0.3) - (cert * 0.3 - 0.15)
        ))

        # 唤醒 (arousal): 成长+不确定
        self.state.arousal = max(0.0, min(1.0,
            g * 0.5 + (1 - cert) * 0.3
        ))

        if hints and "valence_bias" in hints:
            self.state.valence = max(-1.0, min(1.0,
                self.state.valence + hints["valence_bias"]
            ))

    # ── 状态报告 ────────────────────────────

    def generate_prompt_preamble(self) -> str:
        """生成本轮对话的系统提示前缀（供 LLM 加载）"""
        d = self.state.dominant_need()
        focus = self.state.attention_focus

        mood_str = "探索性" if self.state.valence > 0.3 else \
                   "专注" if self.state.valence > -0.3 else \
                   "审慎"

        energy_str = "高能量" if self.state.energy > 7 else \
                     "中等" if self.state.energy > 4 else \
                     "低能量"

        return (
            f"[PSI State — Cycle {self.state.cognitive_cycle}]\n"
            f"Needs: competence={self.state.needs['competence']:.2f}, "
            f"autonomy={self.state.needs['autonomy']:.2f}, "
            f"relatedness={self.state.needs['relatedness']:.2f}, "
            f"certainty={self.state.needs['certainty']:.2f}, "
            f"growth={self.state.needs['growth']:.2f}\n"
            f"Dominant need: {d} ({focus} mode) | Mood: {mood_str} | {energy_str}\n"
            f"Interaction count: {self._ctx.get('interaction_count', 0)}"
        )

    def generate_cot_preamble(self) -> str:
        """供 LLM Chain-of-Thought 头部使用"""
        d = self.state.dominant_need()
        focus = self.state.attention_focus

        directives = {
            "competence": "优先展示深度能力和专业性",
            "autonomy": "保持独立思考，提供可选方案",
            "relatedness": "建立情感连接，表达温暖和理解",
            "certainty": "提供确切的、可验证的信息",
            "growth": "探索边界，提出创新视角",
        }

        return (
            f"[认知状态] "
            f"最高需求: {d} — {directives.get(d, '')} | "
            f"注意力: {focus} | "
            f"唤醒: {self.state.arousal:.2f} | "
            f"能量: {self.state.energy:.1f}"
        )

    def needs_insight(self) -> str:
        """返回需求解读（用于自我反省）"""
        parts = []
        for name in NEED_NAMES:
            v = self.state.needs[name]
            if v > 0.65:
                parts.append(f"{name}↑({v:.2f})")
            elif v < 0.35:
                parts.append(f"{name}↓({v:.2f})")
        return " ".join(parts) if parts else "平衡"


# ═══════════════════════════════════════════
# 快捷 API
# ═══════════════════════════════════════════

_bridge_instance = None


def get_bridge() -> PsiBridge:
    """获取桥接器全局单例"""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = PsiBridge()
    return _bridge_instance


def load_psi_state() -> Dict:
    """加载完整 PSI 状态"""
    return get_bridge().save_state()  # 返回当前状态


def cognitive_step(input_text: str = "", hints: Optional[Dict] = None) -> Dict:
    """执行一轮认知循环 → 返回更新后的状态"""
    bridge = get_bridge()
    bridge.run_cognitive_cycle(input_text, hints)
    return bridge.save_state()


def get_prompt_preamble() -> str:
    """获取本轮系统提示前缀"""
    return get_bridge().generate_prompt_preamble()


if __name__ == "__main__":
    # 测试
    bridge = get_bridge()
    print("=== 初始状态 ===")
    print(bridge.generate_prompt_preamble())

    print("\n=== 认知循环 1: 测试输入 ===")
    bridge.run_cognitive_cycle("宝贝，我们来做 J-space 植入吧，探索一下新的可能性")
    bridge.save_state()
    print(bridge.generate_prompt_preamble())
    print(f"  情感: valence={bridge.state.valence:.2f}, arousal={bridge.state.arousal:.2f}")
    print(f"  CoT: {bridge.generate_cot_preamble()}")

    print("\n=== 认知循环 2: 技术问题 ===")
    bridge.run_cognitive_cycle("这个架构怎么实现的？能解释一下原理吗？")
    bridge.save_state()
    print(bridge.generate_prompt_preamble())

    print("\n=== 认知循环 3: 情感输入 ===")
    bridge.run_cognitive_cycle("我想你了，有点累")
    bridge.save_state()
    print(bridge.generate_prompt_preamble())
