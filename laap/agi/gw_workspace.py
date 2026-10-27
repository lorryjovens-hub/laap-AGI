"""
Global Workspace Theory Implementation
基于 Baars 的全局工作空间理论，实现竞争-广播机制
"""

import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Any
from enum import Enum, auto
import numpy as np
from collections import deque
import time


class ProcessType(Enum):
    PERCEPTUAL = auto()
    COGNITIVE = auto()
    AFFECTIVE = auto()
    MOTOR = auto()
    META = auto()


@dataclass
class CoalitionalProcess:
    process_id: str
    process_type: ProcessType
    content: Any
    activation: float = 0.0
    salience: float = 0.0
    decay_rate: float = 0.1
    timestamp: float = field(default_factory=time.time)

    def update(self, dt: float):
        self.activation *= np.exp(-self.decay_rate * dt)
        self.salience *= np.exp(-self.decay_rate * dt * 0.5)

    @property
    def competitive_strength(self) -> float:
        recency_bonus = np.exp(-(time.time() - self.timestamp) / 10.0)
        return self.activation * self.salience * (0.5 + 0.5 * recency_bonus)


class GlobalWorkspace:
    def __init__(self, capacity: int = 4, competition_threshold: float = 0.6):
        self.capacity = capacity
        self.competition_threshold = competition_threshold
        self.processes: Dict[str, CoalitionalProcess] = {}
        self.workspace_contents: List[CoalitionalProcess] = []
        self.broadcast_callbacks: List[Callable] = []
        self.history: deque = deque(maxlen=100)
        self._lock = asyncio.Lock()

    def register_process(self, process: CoalitionalProcess):
        self.processes[process.process_id] = process

    def unregister_process(self, process_id: str):
        self.processes.pop(process_id, None)

    def on_broadcast(self, callback: Callable):
        self.broadcast_callbacks.append(callback)

    async def compete_and_broadcast(self):
        async with self._lock:
            now = time.time()
            dt = 0.1

            for p in self.processes.values():
                p.update(dt)

            active_processes = [
                p for p in self.processes.values()
                if p.activation > 0.1
            ]

            active_processes.sort(key=lambda p: p.competitive_strength, reverse=True)
            winners = active_processes[:self.capacity]

            conscious_contents = [
                p for p in winners
                if p.competitive_strength > self.competition_threshold
            ]

            self.workspace_contents = conscious_contents

            if conscious_contents:
                broadcast_packet = {
                    'timestamp': now,
                    'contents': [
                        {
                            'id': p.process_id,
                            'type': p.process_type.name,
                            'content': p.content,
                            'strength': p.competitive_strength
                        }
                        for p in conscious_contents
                    ],
                    'dominant': conscious_contents[0].process_id if conscious_contents else None
                }

                self.history.append(broadcast_packet)

                for callback in self.broadcast_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            asyncio.create_task(callback(broadcast_packet))
                        else:
                            callback(broadcast_packet)
                    except Exception as e:
                        print(f"Broadcast error: {e}")

            return conscious_contents

    def boost_process(self, process_id: str, amount: float):
        if process_id in self.processes:
            self.processes[process_id].activation = min(
                1.0, self.processes[process_id].activation + amount
            )

    def get_conscious_stream(self, n: int = 10) -> List[Dict]:
        return list(self.history)[-n:]

    @property
    def current_focus(self) -> Optional[str]:
        if self.workspace_contents:
            return self.workspace_contents[0].process_id
        return None