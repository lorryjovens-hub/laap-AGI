"""
LAAP AGI 快速入门示例
=====================

演示如何实例化一个 AGI Agent 并调用其核心认知模块：
世界模型、因果引擎、类比推理、自我模型、记忆系统。

运行:
    python examples/agi_quickstart.py
"""

from __future__ import annotations

from laap.agi.core import create_agi_agent
from laap.agi.world_model import EntityType
from laap.agi.causal import CausalRule


def main() -> None:
    agent = create_agi_agent("Ao", state_dir="./agi_state")
    print(f"Agent '{agent.name}' created. Hermes available: {agent.hermes.hermes_available}")

    # 1. 世界模型：添加一个实体
    entity = agent.world.add_entity(
        name="Lorry",
        entity_type=EntityType.USER,
        properties={"mood": "curious", "trust": 0.8},
    )
    print("World model entity added:", entity.name, "eid:", entity.eid)

    # 2. 因果引擎：添加并触发一条规则
    rule = CausalRule(
        name="greeting_boosts_trust",
        action="greet",
        conditions=[],
        effects=[],
        probability=1.0,
        confidence=0.9,
    )
    agent.causal.learn_rule(rule)
    result = agent.causal.predict("greet", mode="rule")
    print(f"Causal inference fired {len(result['results'])} rule(s)")

    # 3. 类比推理：跨域结构映射
    agent.analogical.encode_domain(
        "water_flow",
        [
            {
                "name": "tank_to_pipe",
                "nodes": [
                    {"name": "tank", "role": "object", "id": "tank"},
                    {"name": "pipe", "role": "object", "id": "pipe"},
                ],
                "edges": [{"source": "tank", "target": "pipe", "kind": "acts_on"}],
            }
        ],
    )
    agent.analogical.encode_domain(
        "information_flow",
        [
            {
                "name": "sensor_to_processor",
                "nodes": [
                    {"name": "sensor", "role": "object", "id": "sensor"},
                    {"name": "processor", "role": "object", "id": "processor"},
                ],
                "edges": [{"source": "sensor", "target": "processor", "kind": "acts_on"}],
            }
        ],
    )
    analogy = agent.analogical.find_analogy("water_flow", "information_flow")
    print(f"Analogy score: {analogy.similarity_score if analogy else 'N/A'}")

    # 4. 记忆系统：写入并读取
    agent.memory_system.encode_episode(
        content="First interaction with Lorry.",
        associations=["demo", "Lorry"],
    )
    similar = agent.memory_system.retrieve_similar("Lorry interaction", max_results=1)
    print(f"Similar memory: {similar[0].content if similar else 'None'}")

    print("\nDemo complete. AGI modules are functional.")


if __name__ == "__main__":
    main()
