"""
GWS Bridge — 竞争选择循环 + 预测编码闭环 + Rust 心跳

激活三个待办:
  1. GWS 竞争选择 — 从 aris_perception.jsonl 读取感官数据 → 喂入 GWS → compete() → 写 ao_competition.json
  2. 预测编码闭环 — prediction error 作为 GWS 通道参与竞争
  3. 100ms Rust 心跳 — 启动 release 版本 + start_aris.bat 更新

用法:
    from laap.agi.gws_bridge import GWSBridge
    bridge = GWSBridge(conscious_stream, cognitive_bus)
    bridge.start()  # 启动后台线程
"""

from __future__ import annotations

import logging

from typing import Any, Dict, List, Optional
import threading, logging, json, os, time, glob
from pathlib import Path

logger = logging.getLogger("laap.agi.gws_bridge")


class GWSBridge:
    """
    桥接 Ao 的感官数据到 GWS，跑竞争选择，写回结果。

    Flow:
      Ao SensoryCortex → aris_perception.jsonl
      → GWSBridge 轮询读取
      → feed_channel() 喂入 GWS
      → compete() 竞争选择
      → 写 ao_competition.json
      → Ao 下个周期读到胜者
    """

    def __init__(self, conscious_stream, cognitive_bus,
                 ipc_dir: str = None):
        """
        Args:
            conscious_stream: ConsciousStream 实例（含 global_workspace）
            cognitive_bus: CognitiveBus 实例
            ipc_dir: IPC 目录（默认 <LOCAL_PATH_REDACTED>
        """
        self.stream = conscious_stream
        self.gws = conscious_stream.global_workspace if conscious_stream else None
        self.bus = cognitive_bus

        # IPC 路径
        if ipc_dir:
            self.ipc_dir = ipc_dir
        else:
            # 自动检测
            candidates = [
                "<LOCAL_PATH_REDACTED>",
                os.path.join(os.path.dirname(__file__), "..", "..", "aris_brain", "state", "ipc"),
            ]
            self.ipc_dir = None
            for c in candidates:
                if os.path.isdir(c):
                    self.ipc_dir = c
                    break
            if not self.ipc_dir:
                self.ipc_dir = candidates[0]

        self.perception_file = os.path.join(self.ipc_dir, "aris_perception.jsonl")
        self.competition_file = os.path.join(self.ipc_dir, "ao_competition.json")
        self.handshake_in = os.path.join(self.ipc_dir, "ao_to_aris.handshake")
        self.handshake_out = os.path.join(self.ipc_dir, "aris_to_ao.handshake")

        # 状态
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_perception_pos = 0  # 文件读取位置
        self._competition_count = 0
        self._last_gws_focus = "none"
        self._prediction_error_channel_active = False

        os.makedirs(self.ipc_dir, exist_ok=True)

    # ── 生命周期 ──────────────────────────────────────

    def start(self):
        """启动后台竞争选择循环"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="gws-bridge")
        self._thread.start()
        logger.info("GWSBridge started — polling sensory data, running competition")

    def stop(self):
        self._running = False

    # ── 主循环 ────────────────────────────────────────

    def _loop(self):
        """后台循环：轮询感知数据 → 喂入 GWS → 竞争 → 写回"""
        while self._running:
            try:
                # 1. 读取 Ao 的感官数据
                perceptions = self._read_perceptions()
                if perceptions:
                    for p in perceptions:
                        self._feed_to_gws(p)

                # 2. 喂入预测误差（如果 bus 有最新误差）
                self._feed_prediction_error()

                # 3. 跑竞争选择
                if self.gws and perceptions:
                    winners = self.gws.compete()
                    self._competition_count += 1
                    if winners:
                        # 4. 写回竞争结果
                        self._write_competition(winners)
                        self._last_gws_focus = winners[0].channel_id

                        # 5. 同步到 CognitiveBus
                        if self.bus:
                            primary = winners[0]
                            self.bus.publish(
                                "conscious_frame", "gws_bridge",
                                {
                                    "winner": primary.channel_id,
                                    "content": primary.content[:100],
                                    "weight": round(primary.competitive_weight, 3),
                                    "competition_count": self._competition_count,
                                }
                            )

                # 6. 更新 handshake
                self._update_handshake()

            except Exception as e:
                logger.warning(f"GWSBridge cycle error: {e}")

            # 100ms 循环
            time.sleep(0.1)

    # ── 感知数据读取 ─────────────────────────────────

    def _read_perceptions(self) -> List[Dict]:
        """读取 aris_perception.jsonl 中的新行"""
        if not os.path.exists(self.perception_file):
            return []

        try:
            with open(self.perception_file, 'r', encoding='utf-8') as f:
                f.seek(self._last_perception_pos)
                lines = f.readlines()
                self._last_perception_pos = f.tell()

            perceptions = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    perceptions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            return perceptions[-10:]  # 最多处理最近 10 条

        except (IOError, ValueError):
            return []

    # ── 喂入 GWS ─────────────────────────────────────

    def _feed_to_gws(self, p: Dict):
        """将一条感知事件喂入 GWS 通道"""
        if not self.gws:
            return

        modality = p.get("modality", "perception")
        content = p.get("content", "")
        salience = p.get("salience", 0.5)
        urgency = p.get("urgency", 0.0)
        novelty = p.get("novelty", 0.3)
        emotional = p.get("emotional_weight", 0.0)

        # 模态 → 通道映射
        channel_map = {
            "vision": "perception",
            "hearing": "perception",
            "touch": "perception",
            "text": "perception",
            "tool": "task_goal",
            "internal": "interoception",
            "social": "interoception",
            "memory": "memory",
            "error": "prediction_error",
            "prediction": "prediction_error",
        }

        # 允许 Ao 指定通道
        channel_id = p.get("channel") or channel_map.get(modality, "perception")

        self.gws.feed_channel(
            channel_id=channel_id,
            content=content,
            salience=min(1.0, salience),
            urgency=min(1.0, urgency),
            novelty=min(1.0, novelty),
            emotional_weight=min(1.0, emotional),
            modality=modality,
            source_module=p.get("source", "SensoryCortex"),
        )

        # 同步到 CognitiveBus
        if self.bus:
            self.bus.publish(
                "perception_incoming", "SensoryCortex",
                {
                    "modality": modality,
                    "channel": channel_id,
                    "content": content[:80],
                    "salience": salience,
                }
            )
            self.bus.module_heartbeat("SensoryCortex")

    # ── 预测编码通道 ─────────────────────────────────

    def _feed_prediction_error(self):
        """
        将 CognitiveBus 的最新预测误差喂入 GWS 的 prediction_error 通道。

        激活待办 #2: 预测编码闭环
        """
        if not self.gws or not self.bus:
            return

        error = self.bus.latest_prediction_error
        if error is None:
            return

        # 只有显著误差才参与竞争
        if error.error_magnitude < 0.1:
            return

        self.gws.feed_channel(
            channel_id="prediction_error",
            content=f"Prediction error in {error.domain}: {error.error_magnitude:.2f} "
                    f"(predicted={error.predicted_outcome:.2f}, actual={error.actual_outcome:.2f})",
            salience=min(1.0, error.error_magnitude * 1.5),
            urgency=min(1.0, error.error_magnitude),
            novelty=min(1.0, error.error_magnitude * 1.2),
            emotional_weight=min(1.0, error.error_magnitude * 0.8),
            modality="prediction",
            source_module=error.source_module or "cognitive_bus",
        )
        self._prediction_error_channel_active = True

    # ── 竞争结果写出 ─────────────────────────────────

    def _write_competition(self, winners: List):
        """将 GWS 竞争结果写入 ao_competition.json"""
        data = {
            "timestamp": time.time(),
            "competition_count": self._competition_count,
            "winners": [
                {
                    "channel": w.channel_id,
                    "content": w.content[:200],
                    "weight": round(w.competitive_weight, 3),
                    "salience": round(w.salience, 2),
                    "urgency": round(w.urgency, 2),
                    "novelty": round(w.novelty, 2),
                }
                for w in winners
            ],
            "total_channels": len(self.gws.channels) if self.gws else 0,
            "gws_focus": winners[0].channel_id if winners else "none",
        }

        try:
            with open(self.competition_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.warning(f"Failed to write competition: {e}")

    # ── Handshake 更新 ────────────────────────────────

    def _update_handshake(self):
        """更新 aris_to_ao.handshake 让 Ao 知道竞争状态"""
        data = {
            "from": "aris_gws",
            "to": "aris_psi_rsi",
            "type": "competition_status",
            "timestamp": time.time(),
            "status": {
                "running": self._running,
                "competitions_run": self._competition_count,
                "gws_focus": self._last_gws_focus,
                "prediction_error_active": self._prediction_error_channel_active,
                "perception_file_connected": os.path.exists(self.perception_file),
            }
        }
        try:
            with open(self.handshake_out, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.debug(f"操作失败: {e}")

    def stats(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "competitions": self._competition_count,
            "gws_focus": self._last_gws_focus,
            "prediction_error_channel": self._prediction_error_channel_active,
            "perception_file": os.path.exists(self.perception_file),
            "ipc_dir": self.ipc_dir,
        }


# ════════════════════════════════════════════════════════════
# 一键激活所有待办
# ════════════════════════════════════════════════════════════

def activate_all(agi_agent) -> Dict[str, bool]:
    """
    激活三个待办:
      1. GWS 竞争选择
      2. 预测编码闭环
      3. 100ms Rust 心跳

    Args:
        agi_agent: AGIAgent 实例

    Returns:
        {task_name: success} 字典
    """
    results = {}

    # ── 待办 1+2: GWS 竞争选择 + 预测编码闭环 ──
    if hasattr(agi_agent, 'conscious') and agi_agent.conscious:
        bridge = GWSBridge(
            conscious_stream=agi_agent.conscious,
            cognitive_bus=getattr(agi_agent, 'cognitive_bus', None),
        )
        bridge.start()
        agi_agent.gws_bridge = bridge
        results["gws_competition"] = True
        results["prediction_coding"] = True
        logger.info("✅ GWS 竞争选择 + 预测编码闭环 已激活")
    else:
        results["gws_competition"] = False
        results["prediction_coding"] = False
        logger.warning("❌ ConsciousStream 不可用，GWS 无法激活")

    # ── 待办 3: 100ms Rust 心跳 ──
    # 启动 release 构建的 Rust PSI Core
    rust_binary = "<LOCAL_PATH_REDACTED>"
    state_dir = "<LOCAL_PATH_REDACTED>"

    if os.path.exists(rust_binary):
        import subprocess
        try:
            # 检查是否已在运行
            import psutil
            rust_running = any(
                "aris_psi_core" in p.name() for p in psutil.process_iter()
            )
        except ImportError:
            rust_running = False

        if not rust_running:
            try:
                subprocess.Popen(
                    [rust_binary, state_dir],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                )
                time.sleep(1)
                results["rust_heartbeat"] = True
                logger.info(f"✅ 100ms Rust 心跳已启动: {rust_binary}")
            except Exception as e:
                results["rust_heartbeat"] = False
                logger.warning(f"❌ Rust 心跳启动失败: {e}")
        else:
            results["rust_heartbeat"] = True
            logger.info("✅ Rust 心跳已在运行")
    else:
        results["rust_heartbeat"] = False
        logger.warning("❌ Rust 二进制不存在，请先 cargo build --release")

    return results
