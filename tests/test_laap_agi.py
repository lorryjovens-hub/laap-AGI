"""
LAAP AGI 模块基础测试
====================

验证从旧版 LAAP 迁移到 laap-AGI 的核心认知模块可被导入并基本可用。
运行:
    python -m pytest tests/test_laap_agi.py -v
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Ensure the repository root is on sys.path when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from laap.agi.core import create_agi_agent
from laap.agi.world_model import EntityType
from laap.agi.causal import CausalRule


def test_core_modules_importable():
    """核心模块应能被无错导入。"""
    from laap.agi import (
        world_model,
        causal,
        analogical,
        self_model,
        memory_system,
        conscious,
        autonomy,
        safety,
        perception,
    )
    assert world_model is not None
    assert causal is not None


def test_create_agi_agent():
    """应能实例化 AGI Agent，且缺少 Hermes/Rust 时优雅降级。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = create_agi_agent("TestAgent", state_dir=tmpdir)
        assert agent.name == "TestAgent"
        assert agent.world is not None
        assert agent.causal is not None
        assert agent.analogical is not None
        assert agent.memory_system is not None


def test_world_model_entity():
    """世界模型应能添加和查询实体。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = create_agi_agent("TestAgent", state_dir=tmpdir)
        entity = agent.world.add_entity(
            name="Lorry",
            entity_type=EntityType.USER,
            properties={"trust": 0.8},
        )
        assert entity.name == "Lorry"
        assert entity.entity_type == EntityType.USER
        # 不同 world model 后端查询接口不同，至少保证返回对象有效
        assert entity.eid


def test_causal_rule():
    """因果引擎应能学习规则并根据动作推理。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = create_agi_agent("TestAgent", state_dir=tmpdir)
        rule = CausalRule(
            name="greet_rule",
            action="greet",
            conditions=[],
            effects=[],
            probability=1.0,
            confidence=0.9,
        )
        agent.causal.learn_rule(rule)
        result = agent.causal.predict("greet", mode="rule")
        assert len(result["results"]) >= 1
        assert result["results"][0]["rule"] == "greet_rule"


def test_analogical_encoding():
    """类比引擎应能编码领域图并尝试寻找类比。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = create_agi_agent("TestAgent", state_dir=tmpdir)
        agent.analogical.encode_domain(
            "domain_a",
            [
                {
                    "name": "a_to_b",
                    "nodes": [
                        {"name": "a", "role": "object", "id": "a"},
                        {"name": "b", "role": "object", "id": "b"},
                    ],
                    "edges": [{"source": "a", "target": "b", "kind": "acts_on"}],
                }
            ],
        )
        agent.analogical.encode_domain(
            "domain_b",
            [
                {
                    "name": "x_to_y",
                    "nodes": [
                        {"name": "x", "role": "object", "id": "x"},
                        {"name": "y", "role": "object", "id": "y"},
                    ],
                    "edges": [{"source": "x", "target": "y", "kind": "acts_on"}],
                }
            ],
        )
        mapping = agent.analogical.find_analogy("domain_a", "domain_b")
        # 简单图可能无法通过阈值，但函数应正常返回 None 或映射对象
        assert mapping is None or hasattr(mapping, "similarity_score")


def test_episodic_memory():
    """情景记忆应能编码和检索。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = create_agi_agent("TestAgent", state_dir=tmpdir)
        agent.memory_system.encode_episode(
            content="Test episode.",
            associations=["test"],
        )
        results = agent.memory_system.retrieve_similar("test episode", max_results=1)
        assert len(results) == 1
        assert "Test episode" in results[0].content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
