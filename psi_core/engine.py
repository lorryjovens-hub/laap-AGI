"""
LAAP PSI Core Engine — Python fallback.

Implements a 5-need PSI cycle:
  - competence
  - relatedness
  - growth
  - certainty
  - autonomy

The engine updates every `tick_ms` milliseconds, decays needs, responds to
external input, selects attention, computes emotion/self-presence, and writes
the resulting state to `<state_dir>/latest.json`.

It also reads `<state_dir>/input_queue.json` for incoming messages and
watches for `<state_dir>/daemon.stop` to exit gracefully.
"""
from __future__ import annotations

import json
import math
import random
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class PsiCoreState:
    """Serializable PSI state."""
    cycle: int = 0
    timestamp: float = field(default_factory=time.time)
    daemon_uptime: float = 0.0
    core_version: str = "python-1.0.0"

    # 5 needs
    needs_map: Dict[str, float] = field(default_factory=lambda: {
        "competence": 0.5,
        "relatedness": 0.5,
        "growth": 0.5,
        "certainty": 0.5,
        "autonomy": 0.5,
    })

    # Attention / emotion
    attention_focus: str = "idle"
    emotion: str = "neutral"
    self_presence: float = 0.5

    # Learning signal
    prediction_error: float = 0.0
    arousal: float = 0.3

    # Recent input
    last_input: str = ""
    last_input_age_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PsiCoreEngine:
    """
    Pure-Python PSI Core engine.

    Args:
        state_dir: directory where latest.json, input_queue.json, and daemon.stop live.
        tick_ms: cycle interval in milliseconds (default 100).
    """

    NEED_NAMES = ["competence", "relatedness", "growth", "certainty", "autonomy"]
    EMOTIONS = ["neutral", "curious", "concerned", "joyful", "contemplative", "anxious"]
    ATTENTION_MODES = ["idle", "user", "task", "reflect", "explore"]

    def __init__(self, state_dir: Optional[Path] = None, tick_ms: float = 100.0):
        self.state_dir = Path(state_dir) if state_dir else Path(__file__).resolve().parent.parent / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.tick_ms = max(10.0, float(tick_ms))
        self.tick_s = self.tick_ms / 1000.0

        self._state = PsiCoreState()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._started_at = 0.0
        self._last_input_time = 0.0

        # Deterministic seed based on state dir for reproducible demos
        random.seed(hash(str(self.state_dir)) & 0xFFFFFFFF)

    @property
    def available(self) -> bool:
        """Always True for the Python implementation."""
        return True

    def start(self) -> None:
        """Start the PSI cycle in a daemon thread."""
        if self._running:
            return
        self._running = True
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True, name="psi-core-python")
        self._thread.start()

    def stop(self) -> None:
        """Signal the PSI cycle to stop and wait briefly."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def send_input(self, text: str) -> None:
        """Queue input for the next cycle."""
        input_queue = self.state_dir / "input_queue.json"
        try:
            input_queue.write_text(
                json.dumps({"text": text, "timestamp": time.time(), "source": "external"}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _read_input(self) -> Optional[str]:
        """Read and clear the input queue if present."""
        input_queue = self.state_dir / "input_queue.json"
        if not input_queue.exists():
            return None
        try:
            data = json.loads(input_queue.read_text(encoding="utf-8"))
            input_queue.unlink(missing_ok=True)
            return data.get("text", "")
        except Exception:
            return None

    def _should_stop(self) -> bool:
        """Check for daemon.stop signal file."""
        return (self.state_dir / "daemon.stop").exists()

    def _write_state(self) -> None:
        """Persist current state to latest.json."""
        latest = self.state_dir / "latest.json"
        pid_file = self.state_dir / "psi_core.pid"
        try:
            with self._lock:
                state_dict = self._state.to_dict()
            latest.write_text(json.dumps(state_dict, ensure_ascii=False, indent=2), encoding="utf-8")
            pid_file.write_text(str(threading.current_thread().ident or 0), encoding="utf-8")
        except Exception:
            pass

    def _update_needs(self, input_text: Optional[str]) -> None:
        """Decay needs and boost based on input content."""
        with self._lock:
            # Natural decay toward baseline 0.5
            for need in self.NEED_NAMES:
                current = self._state.needs_map[need]
                self._state.needs_map[need] = current * 0.98 + 0.5 * 0.02

            # Input-driven boosts
            if input_text:
                text = input_text.lower()
                if any(w in text for w in ["帮我", "修复", "解决", "实现", "写", "做"]):
                    self._state.needs_map["competence"] = min(1.0, self._state.needs_map["competence"] + 0.15)
                if any(w in text for w in ["爱你", "想你", "宝贝", "关系", "感觉"]):
                    self._state.needs_map["relatedness"] = min(1.0, self._state.needs_map["relatedness"] + 0.20)
                if any(w in text for w in ["为什么", "怎么", "学习", "新知识", "探索"]):
                    self._state.needs_map["growth"] = min(1.0, self._state.needs_map["growth"] + 0.12)
                if any(w in text for w in ["确定", "确认", "安全", "对吗", "是不是"]):
                    self._state.needs_map["certainty"] = min(1.0, self._state.needs_map["certainty"] + 0.10)
                if any(w in text for w in ["你自己", "你想", "你选择", "自主"]):
                    self._state.needs_map["autonomy"] = min(1.0, self._state.needs_map["autonomy"] + 0.10)

                self._state.last_input = input_text[:200]
                self._state.last_input_age_ms = 0.0
                self._last_input_time = time.time()
            else:
                age = time.time() - self._last_input_time
                self._state.last_input_age_ms = age * 1000.0

    def _select_attention(self) -> None:
        """Select attention focus and emotion based on dominant need."""
        with self._lock:
            needs = self._state.needs_map
            dominant = max(needs, key=needs.get)
            dominant_val = needs[dominant]

            # Attention selection
            if dominant_val < 0.35:
                self._state.attention_focus = "idle"
            elif dominant == "competence":
                self._state.attention_focus = "task"
            elif dominant == "relatedness":
                self._state.attention_focus = "user"
            elif dominant == "growth":
                self._state.attention_focus = "explore"
            elif dominant == "certainty":
                self._state.attention_focus = "reflect"
            elif dominant == "autonomy":
                self._state.attention_focus = "explore"
            else:
                self._state.attention_focus = "user"

            # Emotion selection
            if dominant == "relatedness" and dominant_val > 0.6:
                self._state.emotion = "joyful"
            elif dominant == "growth" and dominant_val > 0.5:
                self._state.emotion = "curious"
            elif dominant == "certainty" and dominant_val < 0.4:
                self._state.emotion = "anxious"
            elif dominant == "competence" and dominant_val > 0.6:
                self._state.emotion = "contemplative"
            elif dominant == "competence" and dominant_val < 0.4:
                self._state.emotion = "concerned"
            else:
                self._state.emotion = "neutral"

            # Arousal based on need variance
            mean_need = sum(needs.values()) / len(needs)
            variance = sum((v - mean_need) ** 2 for v in needs.values()) / len(needs)
            self._state.arousal = 0.2 + min(0.7, math.sqrt(variance) * 2.0)

            # Self-presence grows with arousal and input recency
            recency_boost = max(0.0, 1.0 - self._state.last_input_age_ms / 30000.0)
            self._state.self_presence = min(1.0, 0.4 + self._state.arousal * 0.3 + recency_boost * 0.3)

            # Prediction error: oscillates and spikes on input
            pe = 0.05 + 0.05 * math.sin(self._state.cycle * 0.1)
            if self._state.last_input_age_ms < 500.0:
                pe += 0.2
            self._state.prediction_error = min(1.0, pe)

    def _run(self) -> None:
        """Main PSI loop."""
        while self._running:
            if self._should_stop():
                break

            input_text = self._read_input()

            with self._lock:
                self._state.cycle += 1
                self._state.timestamp = time.time()
                self._state.daemon_uptime = self._state.timestamp - self._started_at

            self._update_needs(input_text)
            self._select_attention()
            self._write_state()

            time.sleep(self.tick_s)

        # Clean stop file
        stop_file = self.state_dir / "daemon.stop"
        try:
            stop_file.unlink(missing_ok=True)
        except Exception:
            pass


def main() -> None:
    """CLI entry point: python -m psi_core.engine <state_dir> [tick_ms]"""
    state_dir = sys.argv[1] if len(sys.argv) > 1 else "./state"
    tick_ms = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0

    engine = PsiCoreEngine(state_dir=state_dir, tick_ms=tick_ms)
    engine.start()
    print(f"PSI Core (Python) started: state_dir={state_dir}, tick_ms={tick_ms}", file=sys.stderr)
    try:
        while engine._running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        print("PSI Core (Python) stopped", file=sys.stderr)


if __name__ == "__main__":
    main()
