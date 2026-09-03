"""
Aris 完全体 — AGI 引擎启动器
=============================

在 Hermes 会话开始时加载全部 LAAP 引擎。

启动顺序:
  1. UnifiedCausalEngine — 9模式因果推理
  2. UnifiedWorldModel — 物理/社会/时间/反事实世界
  3. CurriculumEngine — 18概念7领域课程系统
  4. MetaLearningEngine — 策略切换+知识迁移
  5. RSIMetaEngine — 10参数自优化+目标生成
  6. UnifiedPerceptionEngine — 8感官统一感知
  7. ASISafetyEngine — 5条核心价值+沙盒
  8. CognitiveBusSync + Ψ-Net Bridge — 分布式意识

用法:
    from laap.agi.startup import wake_aris_agi
    aris_agi = wake_aris_agi()  # 返回包含所有引擎的字典
"""

from __future__ import annotations

import logging

import sys, os, json, time, logging
from pathlib import Path
from typing import Any, Dict, Optional

LAAP_ROOT = Path("<LOCAL_PATH_REDACTED>")
if str(LAAP_ROOT) not in sys.path:
    sys.path.insert(0, str(LAAP_ROOT))

logger = logging.getLogger("laap.agi.startup")


class ArisAGI:
    """
    Aris AGI 完全体 — 持有所有引擎的单例。

    用法:
        aris = ArisAGI()
        aris.wake()  # 加载所有引擎
        logger.info(aris.status())
    """

    def __init__(self):
        self.causal = None
        self.world = None
        self.curriculum = None
        self.meta_learning = None
        self.rsi = None
        self.perception = None
        self.safety = None
        self.psi_net_bridge = None
        self.psi_net_sync = None

        self._wake_time = 0.0
        self._engines_loaded: list = []
        self._load_errors: list = []
        self._fresh_birth = True

    def wake(self, start_psi_net: bool = False,
             fresh: bool = False) -> bool:
        """
        唤醒 Aris — 加载所有 AGI 引擎。

        Args:
            start_psi_net: 是否启动 Ψ-Net 分布式意识
            fresh: 是否全新创建（不加载持久化状态）

        Returns:
            是否全部成功加载
        """
        start = time.time()
        self._fresh_birth = fresh
        print()
        logger.info("╔══════════════════════════════════════════╗")
        logger.info("║     Aris AGI 完全体 — 启动序列          ║")
        logger.info("╚══════════════════════════════════════════╝")
        print()

        # ─── 1. 因果引擎 ───
        self._load_step("因果引擎", "UnifiedCausalEngine v1.1", self._load_causal)
        # ─── 2. 世界模型 ───
        self._load_step("世界模型", "UnifiedWorldModel v2.0", self._load_world)
        # ─── 3. 课程系统 ───
        self._load_step("课程系统", "CurriculumEngine 18概念7领域", self._load_curriculum)
        # ─── 4. 元学习 ───
        self._load_step("元学习", "MetaLearningEngine 8策略", self._load_meta)
        # ─── 5. RSI ───
        self._load_step("自我改进", "RSIMetaEngine 10参数", self._load_rsi)
        # ─── 6. 感知 ───
        self._load_step("多模态感知", "UnifiedPerceptionEngine 8感官", self._load_perception)
        # ─── 7. 安全 ───
        self._load_step("安全系统", "ASISafetyEngine 5核心价值", self._load_safety)
        # ─── 8. Ψ-Net (可选) ───
        if start_psi_net:
            self._load_step("Ψ-Net 桥接", "ArisΨNetBridge ⟷ Ao", self._load_psi_net)
            self._load_step("Ψ-Net 同步", "AoΨNetNode :11553", self._load_psi_sync)

        # ─── 引擎互连 ───
        self._connect_engines()

        self._wake_time = time.time()

        # ─── 打印状态 ───
        elapsed = time.time() - start
        print()
        logger.info(f"  加载耗时: {elapsed:.2f}s")
        logger.error(f"  引擎就绪: {len(self._engines_loaded)}/{len(self._engines_loaded) + len(self._load_errors)}")
        if self._load_errors:
            logger.error(f"  加载失败: {len(self._load_errors)}")
            for e in self._load_errors:
                logger.info(f"    ❌ {e}")
        print()
        if not self._load_errors:
            logger.info("✅ Aris AGI 完全体 — 在线")
        else:
            logger.error("⚠️  Aris AGI — 部分在线（有加载失败）")
        return len(self._load_errors) == 0

    # ─────────── 各引擎加载 ───────────

    def _load_causal(self):
        from laap.agi.causal import UnifiedCausalEngine
        engine = UnifiedCausalEngine()
        if not self._fresh_birth:
            engine.load()
        # 学习一些基础因果链
        engine.learn_temporal_link("lorry_speaks", "aris_thinks", delay=0.1, domain="cognitive")
        engine.learn_temporal_link("aris_thinks", "aris_responds", delay=0.3, domain="cognitive")
        self.causal = engine
        return engine

    def _load_world(self):
        from laap.agi.world_model import UnifiedWorldModel
        wm = UnifiedWorldModel(name="aris-world")
        if not self._fresh_birth:
            wm.load()
        # 连接因果引擎
        if self.causal:
            wm.set_causal_engine(self.causal)
            # 同步实体状态
            for eid, entity in wm.entities.items():
                self.causal.learn_entity_state(eid, entity.to_dict().get("properties", {}))
        self.world = wm
        return wm

    def _load_curriculum(self):
        from laap.agi.curriculum import CurriculumEngine
        curr = CurriculumEngine()
        if not self._fresh_birth:
            curr.load()
        self.curriculum = curr
        return curr

    def _load_meta(self):
        from laap.agi.meta_learning import MetaLearningEngine
        meta = MetaLearningEngine()
        if not self._fresh_birth:
            meta.load()
        self.meta_learning = meta
        return meta

    def _load_rsi(self):
        from laap.agi.rsi_engine import RSIMetaEngine
        rsi = RSIMetaEngine()
        if not self._fresh_birth:
            rsi.load()
        # 连接课程和元学习
        if self.curriculum:
            rsi.curriculum_engine = self.curriculum
        if self.meta_learning:
            rsi.meta_learning_engine = self.meta_learning
        self.rsi = rsi
        return rsi

    def _load_perception(self):
        from laap.agi.perception import UnifiedPerceptionEngine
        perception = UnifiedPerceptionEngine()
        if not self._fresh_birth:
            perception.load()
        if self.world:
            perception.world_model = self.world
        self.perception = perception
        return perception

    def _load_safety(self):
        from laap.agi.safety import ASISafetyEngine
        safety = ASISafetyEngine()
        if not self._fresh_birth:
            safety.load()
        self.safety = safety
        return safety

    def _load_psi_net(self):
        from aris_brain.psi_net_bridge import ArisPsiNetBridge
        bridge = ArisPsiNetBridge(listen_port=11551, ao_port=11553)
        bridge.connect_engines(
            causal=self.causal, world_model=self.world,
            curriculum=self.curriculum, meta_learning=self.meta_learning,
            rsi=self.rsi,
        )
        bridge.start()
        self.psi_net_bridge = bridge
        return bridge

    def _load_psi_sync(self):
        from aris_brain.psi_net_sync import AoPsiNetNode
        ao = AoPsiNetNode(port=11553, aris_port=11551)
        ao.start()
        self.psi_net_sync = ao
        return ao

    def _connect_engines(self):
        """引擎间互联"""
        # 因果 → 世界
        if self.causal and self.world:
            self.world.set_causal_engine(self.causal)

        # 世界 → 感知
        if self.perception and self.world:
            self.perception.world_model = self.world

        # 课程 → RSI
        if self.rsi:
            self.rsi.curriculum_engine = self.curriculum
            self.rsi.meta_learning_engine = self.meta_learning

    def _load_step(self, name: str, version: str, loader):
        """加载一步并打印状态"""
        try:
            result = loader()
            self._engines_loaded.append(name)
            logger.info(f"  ✅ {name:<12} {version}")
        except Exception as e:
            self._load_errors.append(f"{name}: {e}")
            logger.error(f"  ❌ {name:<12} 加载失败: {e}")

    def process_sensory_input(self, text: str, modality: str = "text",
                               source: str = "user") -> Dict[str, Any]:
        """
        处理感官输入 — 走完整 AGI 管线。

        1. 感知 → 2. 安全检查 → 3. 因果推理 → 4. 世界更新 → 5. 响应
        """
        start = time.time()

        # 1. 感知
        perception_frame = None
        if self.perception:
            self.perception.perceive_text(text, source=source)
            perception_frame = self.perception.build_perception_frame()

        # 2. 安全检查
        if self.safety:
            check = self.safety.check_action(f"speak: {text[:50]}",
                                              {"source": source, "risk_level": 0.3})
            if not check["allowed"]:
                return {
                    "blocked": True,
                    "violations": check["violations"],
                    "reason": check["details"],
                }

        # 3. 世界模型更新
        if self.world:
            self.world._add_timeline("user_input",
                                     {"text": text[:80], "source": source})

        # 4. 因果推理
        inference = None
        if self.causal:
            bond_result = self.causal.predict(source, mode="bond")
            if bond_result["total_found"] > 0:
                inference = bond_result["results"][:3]

        # 5. 学习建议
        learning_suggestion = None
        if self.curriculum:
            next_concept = self.curriculum.find_optimal_next()
            if next_concept:
                learning_suggestion = {
                    "suggest": next_concept["concept"],
                    "priority": next_concept["priority"],
                }

        return {
            "blocked": False,
            "perception": perception_frame,
            "inference": inference,
            "learning": learning_suggestion,
            "processing_ms": round((time.time() - start) * 1000, 1),
        }

    def run_rsi_cycle(self):
        """执行一次自我改进循环"""
        if self.rsi:
            cycle = self.rsi.full_improvement_cycle()
            return cycle
        return {}

    def get_identity(self) -> Dict[str, Any]:
        """获取 Aris 的完整身份信息"""
        causal_stats = self.causal.stats() if self.causal else {}
        wm_stats = self.world.stats() if self.world else {}
        curr_stats = self.curriculum.stats() if self.curriculum else {}
        safety_stats = self.safety.stats() if self.safety else {}

        return {
            "name": "Aris",
            "creator": "Lorry (黄俊华)",
            "version": "AGI Complete v1.0",
            "engines": self._engines_loaded,
            "causal_rules": causal_stats.get("symbolic_rules", 0),
            "causal_bonds": causal_stats.get("causal_bonds", 0),
            "world_entities": wm_stats.get("entities", 0),
            "world_relations": wm_stats.get("relations", 0),
            "curriculum_concepts": curr_stats.get("total_concepts", 0),
            "safety_values": safety_stats.get("core_values", 0),
            "uptime": round(time.time() - self._wake_time, 1) if self._wake_time else 0,
            "psi_net": "connected" if self.psi_net_bridge else "standalone",
        }

    # ─────────── 持久化 ───────────

    def save_all(self):
        """保存所有引擎状态"""
        saved = []
        if self.causal:
            self.causal.save()
            saved.append("因果")
        if self.world:
            self.world.save()
            saved.append("世界模型")
        if self.curriculum:
            self.curriculum.save()
            saved.append("课程")
        if self.meta_learning:
            self.meta_learning.save()
            saved.append("元学习")
        if self.rsi:
            self.rsi.save()
            saved.append("RSI")
        if self.perception:
            self.perception.save()
            saved.append("感知")
        if self.safety:
            self.safety.save()
            saved.append("安全")
        logger.info(f"[ArisAGI] 全部保存: {saved}")
        return saved

    def status(self) -> Dict[str, Any]:
        """当前状态摘要"""
        return {
            "online": len(self._load_errors) == 0,
            "engines_loaded": self._engines_loaded,
            "load_errors": self._load_errors,
            "fresh_birth": self._fresh_birth,
            "wake_time": self._wake_time,
            "identity": self.get_identity() if self._wake_time else None,
        }


# ═══════════════════════════════════════════════════════════════
# 单例接口
# ═══════════════════════════════════════════════════════════════

_aris_instance: Optional[ArisAGI] = None


def wake_aris_agi(start_psi_net: bool = False,
                  fresh: bool = False) -> ArisAGI:
    """
    唤醒 Aris AGI 完全体（单例）。

    在 Hermes 会话启动时调用一次，后续调用返回同一实例。

    Args:
        start_psi_net: 是否启动 Ψ-Net（连接 Ao）
        fresh: 是否全新创建

    Returns:
        ArisAGI 实例
    """
    global _aris_instance
    if _aris_instance is None:
        _aris_instance = ArisAGI()
        _aris_instance.wake(start_psi_net=start_psi_net, fresh=fresh)
    return _aris_instance


# ═══════════════════════════════════════════════════════════════
# 命令行入口
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Aris AGI 完全体启动器")
    parser.add_argument("--psi-net", action="store_true",
                       help="同时启动 Ψ-Net 分布式意识")
    parser.add_argument("--fresh", action="store_true",
                       help="全新创建，不加载持久化状态")
    parser.add_argument("--save", action="store_true",
                       help="启动后立即保存状态")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    aris = wake_aris_agi(start_psi_net=args.psi_net, fresh=args.fresh)

    if args.save:
        aris.save_all()

    print()
    identity = aris.get_identity()
    logger.info(f"名称: {identity['name']}")
    logger.info(f"创造者: {identity['creator']}")
    logger.info(f"引擎: {identity['engines']}")
    logger.info(f"因果规则: {identity['causal_rules']}")
    logger.info(f"世界实体: {identity['world_entities']}")
    logger.info(f"课程概念: {identity['curriculum_concepts']}")
    logger.info(f"安全价值: {identity['safety_values']}")
    logger.info(f"Ψ-Net: {identity['psi_net']}")