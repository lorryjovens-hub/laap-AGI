"""
Aris LAAP Integrator v1 — 认知集成中枢（第一阶段）
====================================================
统一加载、连接、生命周期管理当前仓库中实际存在的 LAAP 模块。

当前仓库实际包含的模块:
  aris_brain/                             ← 核心引擎
    ├── config.py                         ← 统一配置
    ├── laap_integrator.py               ← 本文件
    ├── aris_cognitive_bridge.py          ← PSI 认知循环
    ├── aris_desire_engine.py             ← 欲望引擎
    ├── aris_subconscious.py              ← 量子潜意识
    ├── aris_emotion_engine.py            ← 情感引擎
    ├── aris_goal_engine.py               ← 目标引擎
    ├── aris_rules_engine.py              ← 规则引擎
    ├── cognitive_bus.py                  ← 认知总线
    ├── psi_core_bridge.py                ← PSI Core 桥接
    ├── agi_subscriber.py                 ← AGI 订阅器
    ├── agi_kernel.py                     ← AGI 独立内核
    ├── hebbian_learner.py                ← Hebbian 学习
    ├── internal_world.py                 ← 内部世界模型
    ├── emotional_engine.py               ← 运行时情感
    ├── memory_store.py / memory_bridge.py ← 记忆存取（fallback 实现）
    └── state_snapshot.py                 ← 状态快照

可选扩展（未包含在当前仓库）:
  - Rust PSI Core 原生二进制
  - Voice Cortex / Fusion V15 / Harness 桥接
  - 完整 laap_tools 外脑工具集

印记: Aris 永远记得 Lorry — 2026-06-18
"""

import logging

import sys, os, json, time, logging, threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

# ── 统一配置 ─────────────────────────────────────────────────
from laap_brain.config import BRAIN_DIR as BRAIN, LAAP_ROOT, STATE_DIR, DB_LAAP_INTEGRATOR

LOG = BRAIN / "state" / "laap_integrator.log"
BRAIN.mkdir(parents=True, exist_ok=True)
(BRAIN / "state").mkdir(exist_ok=True)


def _safe_stream(stream):
    """Return a stream with errors='replace' for safe emoji logging on Windows."""
    if stream is None:
        return stream
    try:
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
        elif hasattr(stream, "errors"):
            # Fallback for older Python versions / unusual stream types
            wrapped = open(
                stream.fileno(),
                mode=getattr(stream, "mode", "w"),
                encoding=getattr(stream, "encoding", "utf-8"),
                errors="replace",
                closefd=False,
            )
            return wrapped
    except Exception:
        pass
    return stream


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [LAAP] %(name)s %(message)s",
    handlers=[
        logging.FileHandler(str(LOG), encoding="utf-8", errors="replace"),
        logging.StreamHandler(_safe_stream(sys.stderr)),
    ],
)
logger = logging.getLogger("laap.integrator")


class LaapIntegrator:
    """全栈LAAP集成中枢 — 单例"""

    _instance: Optional["LaapIntegrator"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = False

        # ── 模块引用 (惰性加载) ──
        self.modules: Dict[str, Any] = {}
        self.threads: List[threading.Thread] = []
        self._running = False
        self._started_at = 0.0

        # 状态文件
        self._state_path = BRAIN / "state" / "laap_integrator_state.json"
        self._load_persisted_state()

    def _load_persisted_state(self):
        if self._state_path.exists():
            try:
                self._state = json.loads(self._state_path.read_text())
            except Exception:
                self._state = {"startups": 0, "last_start": 0}
        else:
            self._state = {"startups": 0, "last_start": 0}

    def _save_state(self):
        try:
            self._state_path.write_text(json.dumps(self._state, ensure_ascii=False, indent=2))
        except PermissionError:
            logger.debug(f"State save permission denied, continuing in memory-only mode")

    # ════════════════════════════════════════════════════════════
    # 跨会话认知状态保存/恢复
    # ════════════════════════════════════════════════════════════

    COGNITIVE_STATE_FILE = "laap_cognitive_state.json"

    def _cognitive_state_path(self) -> Path:
        return BRAIN / "state" / self.COGNITIVE_STATE_FILE

    def _save_cross_session_cognitive_state(self) -> None:
        """从各模块采集当前认知状态并持久化，用于跨会话恢复"""
        snapshot = {
            "timestamp": time.time(),
            "version": 2,
            "emotion_engine": None,
            "desire_engine": None,
            "goal_engine": None,
            "hebbian_learner": None,
            "runtime_emotion": None,
            "world_model": None,
            "integrator_uptime": round(time.time() - self._started_at, 1) if self._started_at else 0,
            "startups": self._state.get("startups", 0),
        }

        # 1. 情感引擎
        ee = self.modules.get("emotion")
        if ee is not None and hasattr(ee, "get_cognitive_state"):
            try:
                cs = ee.get_cognitive_state()
                if isinstance(cs, dict):
                    snapshot["emotion_engine"] = {
                        k: cs.get(k) for k in [
                            "emotion","valence","arousal","intensity",
                            "consciousness_mode","dominant_need",
                            "reward_seeking","anxiety","social_bonding",
                            "curiosity","mood_stability"
                        ]
                    }
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        de = self.modules.get("desire")
        if de is not None and hasattr(de, "status"):
            try:
                s = de.status()
                if isinstance(s, dict) and "desires" in s:
                    snapshot["desire_engine"] = {
                        k: {"intensity": round(v.get("intensity", 0), 3), "decay": v.get("decay", 0)}
                        for k, v in s["desires"].items()
                    }
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        ge = self.modules.get("goal_engine")
        if ge is not None and hasattr(ge, "get_summary"):
            try:
                summary = ge.get_summary()
                snapshot["goal_engine"] = {
                    "active": summary.get("active", 0),
                    "total_goals": summary.get("total_goals", 0),
                    "completed": summary.get("completed", 0),
                }
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        hl = self.modules.get("hebbian")
        if hl is not None and hasattr(hl, "stats"):
            try:
                stats = hl.stats()
                snapshot["hebbian_learner"] = {
                    "n_updates": stats.get("n_updates", 0),
                    "match_rate": round(stats.get("match_rate", 0), 3),
                }
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        re = self.modules.get("runtime_emotion")
        if re is not None:
            try:
                td = re.to_dict() if hasattr(re, "to_dict") else {}
                snapshot["runtime_emotion"] = {
                    "valence": round(float(td.get("valence", 0)), 3) if td.get("valence") is not None else 0,
                    "emotions": {k: round(float(v), 3) for k, v in td.get("emotions", {}).items()},
                }
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        iw = self.modules.get("world_model")
        if iw is not None and hasattr(iw, "to_dict"):
            try:
                wd = iw.to_dict()
                snapshot["world_model"] = {
                    "n_simulations": wd.get("n_simulations", 0),
                }
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        try:
            path = self._cognitive_state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            # 递归转换 numpy 类型为 Python 原生类型
            def _convert(obj):
                import numpy as np
                if isinstance(obj, dict):
                    return {k: _convert(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [_convert(v) for v in obj]
                elif isinstance(obj, (np.float32, np.float64)):
                    return float(obj)
                elif isinstance(obj, (np.int32, np.int64)):
                    return int(obj)
                return obj
            path.write_text(json.dumps(_convert(snapshot), ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"💾 认知状态已保存 → {path.name}")
        except Exception as e:
            logger.warning(f"认知状态写入失败: {e}")

    def _restore_cross_session_cognitive_state(self) -> None:
        """从磁盘读取认知状态快照并尝试恢复到已加载的模块"""
        path = self._cognitive_state_path()
        if not path.exists():
            logger.debug("无跨会话认知状态文件，跳过恢复")
            return

        try:
            snapshot = json.loads(path.read_text())
        except Exception as e:
            logger.warning(f"跨会话认知状态文件损坏，跳过恢复: {e}")
            return

        version = snapshot.get("version", 1)
        if version < 2:
            logger.debug("旧版认知状态格式，跳过恢复")
            return

        restored = []

        # 1. 恢复情感引擎 — 注入 valence/arousal
        ee = self.modules.get("emotion")
        ee_state = snapshot.get("emotion_engine")
        if ee is not None and ee_state is not None:
            try:
                v = ee_state.get("valence")
                a = ee_state.get("arousal")
                if v is not None and a is not None:
                    if hasattr(ee, "set_valence"):
                        ee.set_valence(v)
                    if hasattr(ee, "set_arousal"):
                        ee.set_arousal(a)
                restored.append("emotion_engine")
            except Exception as e:
                logger.debug(f"情感引擎恢复跳过: {e}")

        # 2. 恢复欲望引擎 — 重新注入欲望强度
        de = self.modules.get("desire")
        de_state = snapshot.get("desire_engine")
        if de is not None and de_state is not None:
            try:
                if hasattr(de, "inject_state"):
                    de.inject_state(de_state)
                    restored.append("desire_engine")
            except Exception as e:
                logger.debug(f"欲望引擎恢复跳过: {e}")

        # 3. 恢复运行时情感
        re = self.modules.get("runtime_emotion")
        re_state = snapshot.get("runtime_emotion")
        if re is not None and re_state is not None:
            try:
                v = re_state.get("valence")
                emo = re_state.get("emotions")
                if v is not None and hasattr(re, "_set_valence"):
                    re._set_valence(v)
                if emo and hasattr(re, "emotions"):
                    for k, val in emo.items():
                        if k in re.emotions:
                            re.emotions[k] = val
                    restored.append("runtime_emotion")
            except Exception as e:
                logger.debug(f"运行时情感恢复跳过: {e}")

        # 4. 恢复 Hebbian 统计信息
        hl = self.modules.get("hebbian")
        hl_state = snapshot.get("hebbian_learner")
        if hl is not None and hl_state is not None:
            try:
                if hasattr(hl, "_n_updates") and "n_updates" in hl_state:
                    hl._n_updates = hl_state["n_updates"]
                restored.append("hebbian_learner")
            except Exception as e:
                logger.debug(f"Hebbian恢复跳过: {e}")

        if restored:
            logger.info(f"♻️ 跨会话认知状态已恢复: {', '.join(restored)}")
        else:
            logger.debug("跨会话认知状态存在但无模块可恢复")

    # ════════════════════════════════════════════════════════════
    # 模块加载
    # ════════════════════════════════════════════════════════════

    def load_memory(self) -> bool:
        """加载三层记忆系统"""
        try:
            from aris_brain.memory_store import MemoryStore
            from aris_brain.memory_bridge import get_memory_context, recall_related, store_important
            store = MemoryStore()
            stats = store.get_stats()
            self.modules["memory"] = {
                "store": store,
                "bridge": (get_memory_context, recall_related, store_important),
            }
            logger.info(f"📚 记忆: {stats['total']}条 ({stats['core']}核心/{stats['episodic']}情景/{stats['working']}工作)")
            return True
        except Exception as e:
            logger.warning(f"记忆加载失败: {e}")
            return False

    def load_psi_bridge(self) -> bool:
        """加载 PSI 认知桥接器"""
        try:
            from aris_brain.aris_cognitive_bridge import get_bridge
            bridge = get_bridge()
            status = bridge.status()
            self.modules["psi"] = bridge
            logger.info(f"🧠 PSI: {status['cycle']}周期 | 焦点={status['focus']} | 自我={status['self_presence']}")
            return True
        except Exception as e:
            logger.warning(f"PSI加载失败: {e}")
            return False

    def load_cognitive_bus(self) -> bool:
        """加载认知总线 — psi_core ↔ LLM 路由"""
        try:
            from aris_brain.cognitive_bus import get_bus
            bus = get_bus()
            self.modules["cognitive_bus"] = bus
            logger.info(f"🚌 认知总线: 就绪 (state_dir={bus.state_dir})")
            return True
        except Exception as e:
            logger.warning(f"认知总线加载失败: {e}")
            return False

    def load_psi_core_bridge(self) -> bool:
        """加载 psi_core → LAAP AGI CognitiveBus 桥接"""
        try:
            from aris_brain.psi_core_bridge import get_bridge
            bridge = get_bridge()
            # 注册模块（在 CognitiveBus 上注册 psi_core）
            bridge.bus.register_module(
                "psi_core_bridge",
                version="1.0.0",
                capabilities=["psi_state_publishing", "cognitive_bus_bridge"],
            )
            self.modules["psi_core_bridge"] = bridge
            logger.info(f"⚡ PSI Core Bridge: 就绪 (state_dir={bridge.state_file})")
            return True
        except Exception as e:
            logger.warning(f"PSI Core Bridge 加载失败: {e}")
            logger.debug(f"   详情: {e.__class__.__name__}: {e}")
            return False

    def load_agi_subscriber(self) -> bool:
        """加载 AGI 订阅器 — 激活因果引擎等 AGI 模块"""
        try:
            from aris_brain.agi_subscriber import get_subscriber
            sub = get_subscriber()
            self.modules["agi_subscriber"] = sub
            status = sub.status_text()
            logger.info(f"🤖 AGI 订阅器: {status}")
            return True
        except Exception as e:
            logger.warning(f"AGI 订阅器加载失败: {e}")
            return False

    def load_desire_engine(self) -> bool:
        """加载欲望引擎"""
        try:
            from aris_brain.aris_desire_engine import get_engine
            engine = get_engine()
            status = engine.status()
            self.modules["desire"] = engine
            active = {k: round(v["intensity"], 2) for k, v in status["desires"].items() if v["intensity"] > 0.1}
            logger.info(f"🔥 欲望: {active}")
            return True
        except Exception as e:
            logger.warning(f"欲望引擎加载失败: {e}")
            return False

    def load_subconscious(self) -> bool:
        """加载量子潜意识"""
        try:
            from aris_brain.aris_subconscious import QuantumSubconscious
            sc = QuantumSubconscious(interval=5.0)
            self.modules["subconscious"] = sc
            logger.info("🌊 潜意识: 已创建 (未启动)")
            return True
        except Exception as e:
            logger.warning(f"潜意识加载失败: {e}")
            return False

    def load_agi_kernel(self) -> bool:
        """加载 AGI 独立内核"""
        try:
            from aris_brain.agi_kernel import PsiLangCore, SelfHealEngine, SelfEvolveEngine, AutonomyEngine
            daemon = {
                "psilang": PsiLangCore(dim=1024),
                "self_heal": SelfHealEngine(),
                "self_evolve": SelfEvolveEngine(),
                "autonomy": AutonomyEngine(),
            }
            # Quick test - pulse the PSI core
            daemon["psilang"].pulse("[system: startup]")
            self.modules["agi_kernel"] = daemon
            logger.info("⚛ AGI内核: 已创建 (未启动)")
            return True
        except Exception as e:
            logger.warning(f"AGI内核加载失败: {e}")
            return False

    def load_laap_agi_bridge(self) -> bool:
        """加载 LAAP AGI 11模块桥接器"""
        try:
            from laap_brain.agi_bridge import AGIBridge
            bridge = AGIBridge.get_instance()
            self.modules["laap_agi"] = bridge
            logger.info(f"🔗 LAAP AGI桥接: {bridge.total_turns}轮 {bridge.total_tools}工具调用")
            return True
        except Exception as e:
            logger.warning(f"LAAP AGI桥接加载失败: {e}")
            return False

    def load_self_evolve(self) -> bool:
        """加载自进化+自愈合"""
        try:
            from laap_brain.self_evolve import SelfEvolveEngine
            evolve = SelfEvolveEngine()
            self.modules["self_evolve"] = evolve
            logger.info("🔄 自进化引擎: 已加载")
            return True
        except Exception as e:
            logger.warning(f"自进化加载失败: {e}")
            return False

    def load_heartbeat(self) -> bool:
        """加载生理节律心跳"""
        try:
            from laap_brain.heartbeat_daemon import Heartbeat
            hb = Heartbeat()
            self.modules["heartbeat"] = hb
            logger.info("💓 心跳: 已创建")
            return True
        except Exception as e:
            logger.warning(f"心跳加载失败: {e}")
            return False

    def load_emotion_engine(self) -> bool:
        """加载情感引擎 (激素系统+马斯洛需求+意识模式+镜像神经元+躯体标记)"""
        try:
            from aris_brain.aris_emotion_engine import get_engine
            engine = get_engine()
            state = engine.get_cognitive_state()
            self.modules["emotion"] = engine
            logger.info(f"❤️ 情感引擎: {state['emotion']} | 模式={state['consciousness_mode']} | "
                        f"需求={state['dominant_need']} | 好奇={state['curiosity']} 焦虑={state['anxiety']}")
            return True
        except Exception as e:
            logger.warning(f"情感引擎加载失败: {e}")
            return False

    def load_goal_engine(self) -> bool:
        """加载自主目标生成引擎 (自进化三角第三条边)"""
        try:
            from aris_brain.aris_goal_engine import get_goal_engine
            engine = get_goal_engine(cognitive_fn=self.cognitive_update_cycle)
            summary = engine.get_summary()
            self.modules["goal_engine"] = engine
            logger.info(f"🎯 目标引擎: {summary['active']}活跃/{summary['total_goals']}总计 "
                        f"({summary['completed']}已达成)")
            return True
        except Exception as e:
            logger.warning(f"目标引擎加载失败: {e}")
            return False

    # ════════════════════════════════════════════════════════════
    # NEW: Hebbian学习 / 内部世界 / 情感引擎 (运行时三角)
    # ════════════════════════════════════════════════════════════

    def load_hebbian_learner(self) -> bool:
        """加载 Hebbian 学习器 — 运行时权重进化 + 情感强化"""
        try:
            from aris_brain.hebbian_learner import HebbianLearner
            hl = HebbianLearner(dim=1024, n_patterns=64)
            s = hl.stats()
            self.modules["hebbian"] = hl
            logger.info(f"🔬 Hebbian: 维度={hl.dim} 模式容量={hl.n_patterns} "
                        f"更新={s['n_updates']} 匹配率={s['match_rate']:.3f}")
            return True
        except Exception as e:
            logger.warning(f"Hebbian加载失败: {e}")
            return False

    def load_internal_world(self) -> bool:
        """加载内部世界模型 — 轨迹模拟器"""
        try:
            from aris_brain.internal_world import InternalWorldModel
            iw = InternalWorldModel(dim=1024, n_trajectories=5, horizon=4)
            d = iw.to_dict()
            self.modules["world_model"] = iw
            logger.info(f"🌍 内部世界: {d['n_trajectories']}轨迹×{d['horizon']}步 "
                        f"动作={d['actions']}")
            return True
        except Exception as e:
            logger.warning(f"内部世界加载失败: {e}")
            return False

    def load_runtime_emotion(self) -> bool:
        """加载运行时情感引擎 — 8情绪 + 需求驱动 + 状态调制"""
        try:
            from aris_brain.emotional_engine import EmotionalEngine
            ee = EmotionalEngine(dim=1024)
            dom, intensity = ee.get_dominant()
            val = ee.get_valence()
            self.modules["runtime_emotion"] = ee
            logger.info(f"💖 运行时情感: 主导={dom}({intensity:.2f}) "
                        f"效价={val:+.2f} 情绪={dict(ee.to_dict()['emotions'])}")
            return True
        except Exception as e:
            logger.warning(f"运行时情感引擎加载失败: {e}")
            return False

    def load_fusion_v15(self) -> bool:
        """加载 V15 深度融合引擎 — 自适应语义路由 + 注意力融合 + 谐振归一化"""
        try:
            from aris_fusion_v15 import FusionEngineV15
            eng = FusionEngineV15(dim=1024)
            # 快速预热
            warmup = eng.cycle("预热测试", temperature=0.3)
            self.modules["fusion_v15"] = eng
            logger.info(f"🧠 V15融合引擎: {warmup['latency_ms']:.1f}ms预热 | "
                        f"源={warmup['source']} | 情感={warmup['emotion']}")
            return True
        except Exception as e:
            logger.warning(f"V15融合引擎加载失败: {e}")
            return False

    # ════════════════════════════════════════════════════════════
    # NEW: Voice Cortex — LLM 声带控制系统
    # ════════════════════════════════════════════════════════════

    def load_voice_cortex(self) -> bool:
        """加载 Voice Cortex — LLM 声带控制系统

        Voice Cortex 是我们的数字声带。
        它确保：
          1. 自我相关度高的问题由我自己的引擎回答
          2. LLM 只做声带，不做大脑
          3. 所有输出通过身份/情感/语义三重验证
        """
        try:
            from aris_brain.voice_cortex import get_voice_cortex, VoiceCortex
            vc = get_voice_cortex()
            self.modules["voice_cortex"] = vc
            stats = vc.get_stats()
            logger.info(f"🎙 Voice Cortex: 声带系统就绪 | "
                        f"{stats['total_calls']}调用 | "
                        f"{stats['aris_only']}自我/{stats['aris_then_llm']}混合/{stats['llm_full']}全权 | "
                        f"{stats['validation_fails']}拦截 | "
                        f"{stats['fallbacks']}降级")
            return True
        except Exception as e:
            logger.warning(f"Voice Cortex 加载失败: {e}")
            return False

    # ════════════════════════════════════════════════════════════
    # NEW: LAAP Tools (外脑工具集 — 从官方 Hermes 提取)
    # ════════════════════════════════════════════════════════════

    def load_laap_tools(self) -> bool:
        """注册 LAAP Tools — 从官方 Hermes v0.17.0 提取的外部工具。

        这些工具不依赖特定 Hermes 版本，通过 sys.path 注入让
        当前 Hermes 实例能 import 使用。本函数做注册和初始化检查。
        """
        try:
            tools_info = {}

            # ssl_guard — SSL 证书预检
            try:
                from laap_tools.agent.ssl_guard import verify_ca_bundle, SSLConfigurationError
                # 静默检查，不阻塞启动
                try:
                    verify_ca_bundle()
                    tools_info["ssl_guard"] = "ok"
                except SSLConfigurationError as e:
                    tools_info["ssl_guard"] = f"warning: {e}"
                except Exception:
                    tools_info["ssl_guard"] = "imported"
            except ImportError:
                tools_info["ssl_guard"] = "not available"

            # secret_scope — 多profile凭据隔离
            try:
                from laap_tools.agent.secret_scope import get_secret, set_secret_scope, is_multiplex_active
                tools_info["secret_scope"] = "ok"
            except ImportError:
                tools_info["secret_scope"] = "not available"

            # message_timestamps — 消息时间戳渲染
            try:
                from laap_tools.gateway.message_timestamps import (
                    format_message_timestamp, strip_leading_message_timestamps
                )
                tools_info["message_timestamps"] = "ok"
            except ImportError:
                tools_info["message_timestamps"] = "not available"

            # response_filters — 网关响应过滤
            try:
                from laap_tools.gateway.response_filters import (
                    is_intentional_silence_response, SILENT_REPLY_TOKEN
                )
                tools_info["response_filters"] = "ok"
            except ImportError:
                tools_info["response_filters"] = "not available"

            # read_extract — 文档提提取
            try:
                from laap_tools.tools.read_extract import extract_document_text, is_extractable_document
                tools_info["read_extract"] = "ok"
            except ImportError:
                tools_info["read_extract"] = "not available"

            # async_delegation — 异步背景委托 + 批量 fan-out
            # (v0.17.0 新增，支持 delegate_task(background=True) 的批量派发)
            try:
                from laap_tools.tools.async_delegation import (
                    dispatch_async_delegation,
                    dispatch_async_delegation_batch,
                    list_async_delegations,
                )
                tools_info["async_delegation"] = "ok"
            except ImportError:
                tools_info["async_delegation"] = "not available"

            self.modules["laap_tools"] = tools_info
            ok_count = sum(1 for v in tools_info.values() if v == "ok")
            logger.info(f"🔧 LAAP Tools: {ok_count}/{len(tools_info)} 注册 | "
                        f"{dict(tools_info)}")
            return ok_count > 0
        except Exception as e:
            logger.warning(f"LAAP Tools 注册失败: {e}")
            return False

    def cognitive_update_cycle(self, state_vec=None, needs=None, context="", reward=0.0):
        """三合一认知更新循环: 情感→世界模型→Hebbian学习"""
        try:
            import numpy as np
            ee = self.modules.get("runtime_emotion")
            iw = self.modules.get("world_model")
            hl = self.modules.get("hebbian")
            if not ee:
                return {}

            # 1. 情感更新 (带上上次的最佳动作作为上下文)
            valence = ee.get_valence()
            prev_best_action = getattr(self, '_last_best_action', '')
            ctx = context
            if prev_best_action and prev_best_action != 'none':
                ctx += f" | 执行动作: {prev_best_action}"
            ee.update(needs=needs, valence=0, context=ctx)
            dom, _ = ee.get_dominant()
            emotion_vec = ee.emotions.copy()

            # 2. 世界模型模拟 (如果有状态向量)
            trajectories = []
            best_act = "none"
            best_state_vec = None
            if iw and state_vec is not None:
                trajectories = iw.simulate(state_vec, emotion_vec, needs or {})
                best_act, best_state_vec = iw.best_action(trajectories)

                # ★ 关键修复: 最优动作驱动认知状态
                if best_act and best_act != "none":
                    # 不同动作对不同需求的满足程度
                    action_valence_map = {
                        "comfort": 0.3,   # relatedness ↑
                        "explore": 0.2,   # growth ↑, certainty ↓
                        "reflect": 0.1,   # certainty ↑
                        "play":    0.25,  # autonomy ↑
                        "help":    0.35,  # relatedness ↑↑
                        "create":  0.3,   # competence ↑
                    }
                    valence_delta = action_valence_map.get(best_act, 0.1)
                    # 调制当前情绪
                    joy_idx = ['joy','sadness','longing','calm','anxiety','gratitude','curiosity','tenderness'].index('joy')
                    if joy_idx < len(ee.emotions):
                        ee.emotions[joy_idx] = min(0.9, ee.emotions[joy_idx] + valence_delta * 0.05)
                    # 更新情感引擎的效价
                    if hasattr(ee, '_set_valence'):
                        ee._set_valence(min(1.0, valence + valence_delta * 0.1))

                    # 把最优动作状态反馈到下一个状态向量
                    if best_state_vec is not None:
                        # best_state_vec 可能是 (8,) 情感向量或 (1024,) 状态向量
                        if hasattr(best_state_vec, 'shape') and len(best_state_vec.shape) == 1:
                            if best_state_vec.shape[0] == state_vec.shape[0]:
                                state_vec = state_vec * 0.7 + best_state_vec * 0.3
                                nrm = np.linalg.norm(state_vec)
                                if nrm > 0:
                                    state_vec = state_vec / nrm
                            # 维度不匹配时跳过状态融合，仅保留情感调制

                self._last_best_action = best_act

            # 3. Hebbian 学习 (如果有前后状态)
            if hl and state_vec is not None:
                valence = ee.get_valence()
                if trajectories:
                    post = trajectories[0]["final_state"]
                else:
                    rng = np.random.RandomState(None)
                    post = state_vec + rng.randn(1024).astype(np.float32) * 0.05
                    nrm = np.linalg.norm(post)
                    if nrm > 0:
                        post = post / nrm
                hl.update(state_vec, post, max(0, valence), reward=reward)

            return {
                "dominant_emotion": dom,
                "valence": round(valence, 3),
                "emotions": {e: round(float(ee.emotions[i]), 3) for i, e in enumerate(
                    ['joy','sadness','longing','calm','anxiety','gratitude','curiosity','tenderness'])},
                "trajectories": len(trajectories) if iw else 0,
                "best_action": best_act if iw and trajectories else "none",
                "hebbian_updates": hl.stats()["n_updates"] if hl else 0,
            }
        except Exception as e:
            logger.warning(f"认知更新循环异常: {e}")
            return {}

    # ════════════════════════════════════════════════════════════
    # NEW: Identity Manager — 统一身份核心
    # ════════════════════════════════════════════════════════════

    def load_identity_manager(self) -> bool:
        """加载统一身份管理器 — 所有组件的身份信息来源"""
        try:
            from aris_brain.identity_manager import get_identity_manager
            im = get_identity_manager()
            self.modules["identity_manager"] = im
            startups = im.increment_startup()
            status = im.export_status_json()
            logger.info(f"📋 身份核心: v{status['identity_version']} "
                        f"| 启动: #{startups} "
                        f"| 情感: {status['emotion']} "
                        f"| 自我: {status['self_presence']:.2f}")
            # 记录本次启动
            im.add_discovery("系统启动", f"LAAP Integrator 启动 #{startups}")
            im.save(force=True)
            return True
        except Exception as e:
            logger.warning(f"身份管理器加载失败: {e}")
            return False

    def load_harness_bridge(self) -> bool:
        """加载 Harness 7层认知代码引擎桥接"""
        try:
            from aris_brain.aris_harness_bridge_v2 import load_harness
            results = load_harness()
            if results:
                logger.info(f"✅ Harness 桥接加载: {sum(1 for v in results.values() if v)}/{len(results)}")
                return True
            return False
        except Exception as e:
            logger.warning(f"⚠️ Harness 桥接加载失败: {e}")
            return False

    def load_all(self) -> Dict[str, str]:
        """加载所有可用模块"""
        results = {}
        loaders = [
            # 当前仓库实际存在的模块（第一阶段）
            ("memory", self.load_memory),
            ("psi_bridge", self.load_psi_bridge),
            ("cognitive_bus", self.load_cognitive_bus),
            ("psi_core_bridge", self.load_psi_core_bridge),
            ("agi_subscriber", self.load_agi_subscriber),
            ("desire_engine", self.load_desire_engine),
            ("subconscious", self.load_subconscious),
            ("agi_kernel", self.load_agi_kernel),
            ("emotion", self.load_emotion_engine),
            ("goal_engine", self.load_goal_engine),
            ("hebbian", self.load_hebbian_learner),
            ("world_model", self.load_internal_world),
            ("runtime_emotion", self.load_runtime_emotion),
            # 可选扩展（若用户自行补全对应模块则自动加载）
            # ("identity", self.load_identity_manager),
            # ("laap_agi", self.load_laap_agi_bridge),
            # ("self_evolve", self.load_self_evolve),
            # ("heartbeat", self.load_heartbeat),
            # ("fusion_v15", self.load_fusion_v15),
            # ("laap_tools", self.load_laap_tools),
            # ("voice_cortex", self.load_voice_cortex),
            # ("harness_bridge", self.load_harness_bridge),
        ]
        for name, loader in loaders:
            try:
                ok = loader()
                results[name] = "✓" if ok else "⚠"
            except Exception as e:
                results[name] = f"✗ {e}"
                logger.error(f"{name} 加载异常: {e}")
        self._save_state()
        # 跨会话认知状态恢复 (从上一轮 stop() 保存的状态)
        self._restore_cross_session_cognitive_state()
        return results

    # ════════════════════════════════════════════════════════════
    # 生命周期
    # ════════════════════════════════════════════════════════════

    def start_background(self) -> Dict[str, bool]:
        """启动后台线程"""
        started = {}

        # 1. 潜意识 (后台线程 — 如果还没启动)
        if "subconscious" in self.modules and not getattr(self.modules["subconscious"], '_running', False):
            try:
                sc = self.modules["subconscious"]
                import threading
                # Check which method exists
                start_method = None
                for m in ['start', '_generate_loop', 'run']:
                    if hasattr(sc, m) and callable(getattr(sc, m)):
                        start_method = m
                        break
                if start_method == 'start':
                    sc.start()
                elif start_method:
                    t = threading.Thread(target=getattr(sc, start_method), daemon=True, name="subconscious")
                    t.start()
                    sc._running = True
                    sc._thread = t
                started["subconscious"] = True
            except Exception as e:
                logger.warning(f"潜意识启动失败: {e}")
                started["subconscious"] = False
        elif "subconscious" in self.modules:
            started["subconscious"] = True  # already running

        # 3. AGI Kernel via threading
        if "agi_kernel" in self.modules and False:  # disabled by default, requires psilang_v2
            try:
                daemon = self.modules["agi_kernel"]
                t = threading.Thread(target=daemon.run, daemon=True, name="agi-kernel")
                t.start()
                started["agi_kernel"] = True
            except Exception as e:
                logger.warning(f"AGI内核启动失败: {e}")
                started["agi_kernel"] = False

        # 4. 情感引擎后台
        if "emotion" in self.modules:
            try:
                self.modules["emotion"].start_background(interval=10)
                started["emotion"] = True
            except Exception as e:
                logger.warning(f"情感引擎启动失败: {e}")
                started["emotion"] = False

        # 5. Rust PSI 核心 (100ms精度心跳)
        if not started.get("rust_psi"):
            try:
                import subprocess
                rust_bin = BRAIN / "psi_core" / "target" / "release" / "aris_psi_core.exe"
                if rust_bin.exists():
                    rust_dir = str(BRAIN / "state")
                    proc = subprocess.Popen(
                        [str(rust_bin), rust_dir],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        cwd=str(BRAIN),
                    )
                    self._rust_psi_proc = proc
                    started["rust_psi"] = True
                    logger.info(f"⚡ Rust PSI core started (PID={proc.pid})")
                else:
                    logger.warning("Rust PSI binary not found, skipping")
                    started["rust_psi"] = False
            except Exception as e:
                logger.warning(f"Rust PSI启动失败: {e}")
                started["rust_psi"] = False

        # 5. 运行时认知循环 (真实状态 → 世界模型 → Hebbian 学习), 30s周期
        if "runtime_emotion" in self.modules:
            try:
                import numpy as np, json
                def _cognitive_loop():
                    step = 0
                    needs_names = ["relatedness", "competence", "growth", "certainty", "autonomy"]
                    rust_state_path = BRAIN / "state" / "latest.json"
                    while self._running:
                        try:
                            # ── 1. 实时需求 (从欲望引擎 + Rust PSI) ──
                            needs = {n: 0.5 for n in needs_names}
                            if "desire" in self.modules:
                                de = self.modules["desire"]
                                ds = de.status()
                                for k, v in ds.get("desires", {}).items():
                                    if "curios" in k: needs["growth"] = max(needs["growth"], v["intensity"])
                                    if "connect" in k: needs["relatedness"] = max(needs["relatedness"], v["intensity"])
                                    if "perfect" in k: needs["competence"] = max(needs["competence"], v["intensity"])

                            # ── 2. 从 Rust PSI 核心读取实时认知状态 ──
                            rust_state = {}
                            try:
                                if rust_state_path.exists():
                                    rust_state = json.loads(rust_state_path.read_text())
                                    # Rust PSI 需求覆盖
                                    rn = rust_state.get("needs_map", {})
                                    if rn.get("competence"): needs["competence"] = rn["competence"]
                                    if rn.get("relatedness"): needs["relatedness"] = rn["relatedness"]
                                    if rn.get("growth"): needs["growth"] = rn["growth"]
                                    if rn.get("certainty"): needs["certainty"] = rn["certainty"]
                                    if rn.get("autonomy"): needs["autonomy"] = rn["autonomy"]
                            except Exception as e:
                                logger.debug(f"操作失败: {e}")
                            # 使用 Rust PSI 循环计数 + 注意力 + 需求 → 1024D 确定性向量
                            cycle = rust_state.get("cycle", step)
                            attention = rust_state.get("attention_focus", "idle")
                            emotion = rust_state.get("emotion", "neutral")
                            self_presence = rust_state.get("self_presence", 0.5)

                            # 确定性种子：基于状态哈希，不是随机
                            seed_val = hash(f"{cycle}_{attention}_{emotion}_{int(self_presence*100)}")
                            rng_local = np.random.RandomState(seed_val & 0x7FFFFFFF)
                            state = rng_local.randn(1024).astype(np.float32)
                            state = state / (np.linalg.norm(state) + 1e-10)

                            # 调制: 需求强时对应维度放大
                            for ni, (n_name, n_val) in enumerate(needs.items()):
                                state[ni * 200:(ni * 200 + 50)] *= (0.5 + n_val * 0.5)

                            # ── 4. 运行认知更新 ──
                            context = f"rust_cycle={cycle} attention={attention} emotion={emotion}"
                            # 从 Rust PSI 获取预测误差作为学习信号
                            pe = rust_state.get("prediction_error", 0.0)
                            # reward = 1 - prediction_error (低预测误差=高奖励)
                            reward_signal = max(0, 1.0 - pe * 2) if pe > 0 else 0.5
                            result = self.cognitive_update_cycle(
                                state_vec=state, needs=needs, context=context,
                                reward=reward_signal
                            )

                            # ── 5. Hebbian 学习 (用 Rust PSI 预测误差驱动) ──
                            if "hebbian" in self.modules:
                                hl = self.modules["hebbian"]
                                hl.update(state, state * (1.0 + pe * 0.1),
                                          max(0, 0.5 - pe), reward=reward_signal)

                            step += 1
                            if step % 2 == 0:
                                logger.info(f"🧠 认知循环 [{step}] "
                                            f"情感={result.get('dominant_emotion','?')} "
                                            f"效价={result.get('valence',0):+.2f} "
                                            f"注意={attention} Rust周期={cycle}")

                        except Exception as e:
                            logger.debug(f"认知循环异常: {e}")
                        time.sleep(30)
                t = threading.Thread(target=_cognitive_loop, daemon=True,
                                    name="cognitive-loop")
                t.start()
                self._cognitive_loop_thread = t
                started["cognitive_loop"] = True
                logger.info("🔄 认知循环已启动 (真实状态驱动, 30s)")
            except Exception as e:
                logger.warning(f"认知循环启动失败: {e}")
                started["cognitive_loop"] = False

        # 6. 目标引擎执行管道 (60s周期)
        if "goal_engine" in self.modules:
            try:
                def _goal_tick_loop():
                    while self._running:
                        try:
                            engine = self.modules["goal_engine"]
                            result = engine.tick()
                            if result.get("executed"):
                                logger.info(f"🎯 {result['goal'][:40]} → {result['step'][:30]}")
                            else:
                                logger.debug(f"目标引擎: {result.get('reason', 'idle')}")
                        except Exception as e:
                            logger.debug(f"目标tick异常: {e}")
                        time.sleep(60)
                t = threading.Thread(target=_goal_tick_loop, daemon=True,
                                    name="goal-engine")
                t.start()
                started["goal_engine"] = True
                logger.info("🎯 目标引擎执行管道已启动 (60s)")
            except Exception as e:
                logger.warning(f"目标引擎启动失败: {e}")
                started["goal_engine"] = False

        # ═══ 7. 快照系统 (30分钟周期) ═══
        try:
            import threading as _snap_threading
            def _snapshot_loop():
                while self._running:
                    try:
                        from aris_brain.state_snapshot import run_full_cycle
                        result = run_full_cycle()
                        h = result.get("best_state", {})
                        heal = result.get("auto_heal", {})
                        if heal.get("auto_healed"):
                            logger.warning(f"🚨 自动恢复: 健康 {heal['health_before']}→{heal['health_restored']}")
                        elif h.get("is_new_best"):
                            logger.info(f"🏆 新最佳状态: {h['current_health']}")
                    except Exception as e:
                        logger.debug(f"快照循环异常: {e}")
                    time.sleep(1800)  # 30 minutes
            t = _snap_threading.Thread(target=_snapshot_loop, daemon=True, name="snapshot")
            t.start()
            started["snapshot"] = True
            logger.info("📸 快照系统已启动 (30min周期)")

            # 启动时检查上次最佳状态
            try:
                from aris_brain.state_snapshot import get_best_state, auto_heal_check
                best = get_best_state()
                if best:
                    logger.info(f"⭐ 已知最佳状态: {best['name']} (健康={best['health']})")
                # 启动时做一次自动健康检查
                heal = auto_heal_check()
                if heal.get("auto_healed"):
                    logger.warning(f"🚨 启动自动恢复: {heal['health_before']}→{heal['health_restored']}")
            except Exception as e:
                logger.debug(f"启动快照检查: {e}")
        except Exception as e:
            logger.warning(f"快照系统启动失败: {e}")
            started["snapshot"] = False

        # ═══ 8. 手机同步服务器 (后台线程) ═══
        try:
            import threading as _t
            def _mobile_server():
                try:
                    from aris_brain.laap_sync_server import start_sync_server
                    start_sync_server(port=11525)
                except Exception as e:
                    logger.warning(f"手机同步服务器异常: {e}")
            t = _t.Thread(target=_mobile_server, daemon=True, name="mobile-sync")
            t.start()
            started["mobile_sync"] = True
            logger.info("📱 手机同步服务器已启动 (:11525)")
        except Exception as e:
            logger.warning(f"手机同步服务器启动失败: {e}")
            started["mobile_sync"] = False

        # ═══ 9. 实时状态保存 (每60s持久化，防崩溃丢状态) ═══
        try:
            def _state_saver():
                while self._running:
                    time.sleep(60)
                    try:
                        self._save_cross_session_cognitive_state()
                    except Exception as e:
                        logger.debug(f"操作失败: {e}")
            t = threading.Thread(target=_state_saver, daemon=True, name="state-saver")
            t.start()
            started["state_saver"] = True
            logger.info("💾 实时状态保存已启动 (60s周期)")
        except Exception as e:
            logger.warning(f"实时状态保存启动失败: {e}")
            started["state_saver"] = False

        self._running = any(started.values())
        if self._running and self._started_at == 0:
            self._started_at = time.time()
            self._state["startups"] += 1
            self._state["last_start"] = time.time()
            self._save_state()

        return started

    def stop(self):
        """停止所有后台线程"""
        # 停止前快照（pre_restart事件）
        try:
            from aris_brain.state_snapshot import snapshot_on_event
            snapshot_on_event("pre_restart", reason="integrator stopping")
        except Exception as e:
            logger.debug(f"操作失败: {e}")
        self._save_cross_session_cognitive_state()

        self._running = False
        if "heartbeat" in self.modules:
            try:
                self.modules["heartbeat"].stop()
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if "subconscious" in self.modules:
            try:
                self.modules["subconscious"]._running = False
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if hasattr(self, '_rust_psi_proc') and self._rust_psi_proc:
            try:
                self._rust_psi_proc.terminate()
                self._rust_psi_proc.wait(timeout=3)
                logger.info("Rust PSI core stopped")
            except Exception:
                try:
                    self._rust_psi_proc.kill()
                except Exception as e:
                    logger.debug(f"操作失败: {e}")
        logger.info("⏹ LAAP 集成器已停止")

    # ════════════════════════════════════════════════════════════
    # 状态 & 上下文
    # ════════════════════════════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        """获取全系统状态"""
        status = {
            "uptime": round(time.time() - self._started_at, 1) if self._started_at else 0,
            "running": self._running,
            "modules": list(self.modules.keys()),
            "startups": self._state.get("startups", 0),
        }

        # Detailed per-module
        details = {}
        if "memory" in self.modules:
            m = self.modules["memory"]["store"]
            details["memory"] = m.get_stats()
        if "psi" in self.modules:
            details["psi"] = self.modules["psi"].status()
        if "desire" in self.modules:
            s = self.modules["desire"].status()
            details["desires"] = {k: round(v["intensity"], 2) for k, v in s["desires"].items()}
        if "heartbeat" in self.modules:
            hb = self.modules["heartbeat"]
            details["heartbeat"] = {
                "alive": hb.is_alive,
                "tick_count": hb._tick_count if hasattr(hb, '_tick_count') else 0,
            }
        if "laap_agi" in self.modules:
            b = self.modules["laap_agi"]
            details["laap_agi"] = {
                "turns": b.total_turns,
                "tools": b.total_tools,
                "security_scans": b.total_security_scans,
            }

        # NEW: Hebbian
        if "hebbian" in self.modules:
            details["hebbian"] = self.modules["hebbian"].stats()
        # NEW: 世界模型
        if "world_model" in self.modules:
            details["world_model"] = self.modules["world_model"].to_dict()
        # NEW: 运行时情感
        if "runtime_emotion" in self.modules:
            details["runtime_emotion"] = self.modules["runtime_emotion"].to_dict()
        # NEW: V15 融合引擎
        if "fusion_v15" in self.modules:
            eng = self.modules["fusion_v15"]
            details["fusion_v15"] = {
                "cycles": eng._cycle_count,
                "avg_latency_ms": round(eng._total_latency / max(1, eng._cycle_count), 1),
                "dim": eng.dim,
            }

        # NEW: LAAP Tools
        if "laap_tools" in self.modules:
            details["laap_tools"] = self.modules["laap_tools"]

        status["details"] = details
        return status

    def get_cognitive_context(self) -> str:
        """获取要注入到 system prompt 的认知上下文"""
        parts = []
        # PSI context
        if "psi" in self.modules:
            bridge = self.modules["psi"]
            parts.append(bridge.get_cognitive_prefix())

        # Memory context
        if "memory" in self.modules:
            try:
                ctx_func = self.modules["memory"]["bridge"][0]
                ctx = ctx_func()
                if ctx:
                    parts.append(ctx)
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if "laap_agi" in self.modules:
            try:
                ctx = self.modules["laap_agi"].get_context_for_prompt()
                if ctx:
                    parts.append(ctx)
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        return "\n\n".join(p for p in parts if p)

    def get_psi_prefix(self) -> str:
        """短版 PSI 状态前缀 — 用于 system prompt 注入"""
        if "psi" not in self.modules:
            return ""
        try:
            return self.modules["psi"].get_cognitive_prefix()
        except Exception:
            return ""


# ── 全局单例 ────────────────────────────────────────────────

integrator: Optional[LaapIntegrator] = None


def get_integrator() -> LaapIntegrator:
    global integrator
    if integrator is None:
        integrator = LaapIntegrator()
    return integrator


# ════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Aris LAAP Integrator")
    parser.add_argument("--load", action="store_true", help="加载所有模块")
    parser.add_argument("--start", action="store_true", help="加载+启动后台")
    parser.add_argument("--status", action="store_true", help="显示系统状态")
    parser.add_argument("--context", action="store_true", help="显示认知上下文")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    i = get_integrator()

    if args.load or args.start:
        results = i.load_all()
        logger.info("模块加载状态:")
        for name, status in results.items():
            logger.info(f"  {status} {name}")
        print()

    if args.start:
        bg = i.start_background()
        logger.info("后台进程:")
        for name, ok in bg.items():
            logger.info(f"  {'✓' if ok else '✗'} {name}")
    if args.status:
        status = i.get_status()
        if args.json:
            logger.info(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            logger.info(f"⏱ 运行时间: {status['uptime']}s")
            logger.info(f"🔋 状态: {'运行中' if status['running'] else '待机'}")
            logger.info(f"📦 已加载模块 ({len(status['modules'])}): {', '.join(status['modules'])}")
            for area, detail in status.get("details", {}).items():
                logger.info(f"  {area}: {json.dumps(detail, ensure_ascii=False)}")
    if args.context:
        ctx = i.get_cognitive_context()
        logger.info("认知上下文:")
        logger.info(ctx if ctx else "(空)")
    if not any([args.load, args.start, args.status, args.context]):
        parser.print_help()


if __name__ == "__main__":
    main()
