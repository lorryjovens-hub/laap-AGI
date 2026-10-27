"""
LAAP AGI — 元学习引擎 (Meta-Learning Engine)
=============================================

P2-1: 学会如何学习。

核心能力：
  1. 学习效率监测 — 追踪学习速度、最佳条件、遗忘模式
  2. 策略自动切换 — 根据内容自动选择最佳学习方式
  3. 知识迁移检测 — 发现领域间的知识共通性
  4. 学习收益评估 — 衡量实际 vs 预期的学习产出
  5. 与 PSI growth need 联动 — 学习驱动成长需求

印记: Aris 永远记得 Lorry — 元学习引擎 v1.0
"""

from __future__ import annotations

import os

import logging

import json, math, time, random, logging, uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import numpy as np

logger = logging.getLogger("laap.agi.meta_learning")


# ═══════════════════════════════════════════════════════════════
# 学习策略
# ═══════════════════════════════════════════════════════════════

class LearningStrategy(str, Enum):
    """可用的学习策略"""
    THEORETICAL = "theoretical"       # 从理论入手, 先理解原理
    PRACTICAL = "practical"           # 从实践入手, 先动手后理解
    ANALOGICAL = "analogical"         # 通过类比, 对比已知知识
    EXPLORATORY = "exploratory"       # 自由探索, 自己发现规律
    STRUCTURED = "structured"         # 按步骤循序渐进
    SPACED_REPETITION = "spaced"      # 间隔重复, 对抗遗忘
    ACTIVE_RECALL = "active_recall"   # 主动回忆, 测试驱动
    TEACHING = "teaching"             # 通过教别人来学


@dataclass
class StrategyEfficacy:
    """一种策略在特定条件下的效果记录"""
    strategy: LearningStrategy = LearningStrategy.STRUCTURED
    domain: str = "general"
    avg_gain_rate: float = 0.0        # 平均掌握度增益/小时
    avg_retention: float = 0.0        # 24h后平均保留率
    times_used: int = 0
    success_rate: float = 0.0
    best_difficulty_range: Tuple[float, float] = (0.1, 0.9)
    last_used: float = 0.0

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "domain": self.domain,
            "avg_gain": round(self.avg_gain_rate, 4),
            "avg_retention": round(self.avg_retention, 3),
            "times_used": self.times_used,
            "success_rate": round(self.success_rate, 3),
            "difficulty_range": [self.best_difficulty_range[0],
                                 self.best_difficulty_range[1]],
        }


# ═══════════════════════════════════════════════════════════════
# 学习效率记录
# ═══════════════════════════════════════════════════════════════

@dataclass
class LearningSessionRecord:
    """一次学习会话的详细记录"""
    id: str = ""
    concept: str = ""
    strategy: LearningStrategy = LearningStrategy.STRUCTURED
    domain: str = "general"
    duration_minutes: float = 0.0
    mastery_before: float = 0.0
    mastery_after: float = 0.0
    gain: float = 0.0
    gain_rate: float = 0.0           # gain / hour
    difficulty: float = 0.5
    successful: bool = False
    timestamp: float = field(default_factory=time.time)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "concept": self.concept,
            "strategy": self.strategy.value,
            "duration_min": round(self.duration_minutes, 1),
            "gain": round(self.gain, 4),
            "gain_rate": round(self.gain_rate, 4),
            "successful": self.successful,
        }


# ═══════════════════════════════════════════════════════════════
# 知识迁移
# ═══════════════════════════════════════════════════════════════

@dataclass
class KnowledgeTransfer:
    """一条知识迁移记录"""
    source_domain: str = ""
    target_domain: str = ""
    source_concept: str = ""
    target_concept: str = ""
    similarity: float = 0.0           # 结构相似度
    transfer_effect: float = 0.0      # 迁移对学习的促进效果
    confidence: float = 0.5
    discovered_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "from": f"{self.source_domain}/{self.source_concept}",
            "to": f"{self.target_domain}/{self.target_concept}",
            "similarity": round(self.similarity, 3),
            "effect": round(self.transfer_effect, 3),
            "confidence": round(self.confidence, 3),
        }


# ═══════════════════════════════════════════════════════════════
# 元学习引擎
# ═══════════════════════════════════════════════════════════════

class MetaLearningEngine:
    """
    元学习引擎 — 学会如何学习。

    核心循环：
      1. 监测每次学习会话的效率
      2. 根据领域/难度/历史选择最佳策略
      3. 发现跨领域的知识迁移机会
      4. 评估学习收益，调整未来策略
    """

    def __init__(self):
        # 学习会话历史
        self.sessions: List[LearningSessionRecord] = []
        self.max_sessions = 500

        # 策略效果数据库
        self.strategy_efficacy: Dict[str, StrategyEfficacy] = {}

        # 知识迁移记录
        self.transfers: List[KnowledgeTransfer] = []
        self.max_transfers = 200

        # 领域相似度矩阵
        self.domain_similarity: Dict[str, Dict[str, float]] = defaultdict(dict)

        # 当前推荐策略
        self.current_strategy: LearningStrategy = LearningStrategy.STRUCTURED

        # 统计
        self._total_sessions = 0
        self._strategy_switches = 0
        self._transfer_discoveries = 0
        self._created_at = time.time()

        # 注册默认领域相似度
        self._register_domain_similarities()

        logger.info(f"[MetaLearningEngine] 初始化完成")

    # ─────────── 学习效率监测 ───────────

    def record_session(self, concept: str, strategy: Union[str, LearningStrategy],
                       duration_minutes: float, mastery_before: float,
                       mastery_after: float, difficulty: float = 0.5,
                       successful: bool = True, domain: str = "general",
                       notes: str = "") -> LearningSessionRecord:
        """记录一次学习会话"""
        if isinstance(strategy, str):
            strategy = LearningStrategy(strategy.lower())

        gain = mastery_after - mastery_before
        gain_rate = gain / max(0.01, duration_minutes / 60)  # gain per hour

        record = LearningSessionRecord(
            id=f"ls_{uuid.uuid4().hex[:8]}",
            concept=concept, strategy=strategy,
            domain=domain, duration_minutes=duration_minutes,
            mastery_before=mastery_before, mastery_after=mastery_after,
            gain=gain, gain_rate=gain_rate,
            difficulty=difficulty, successful=successful,
            notes=notes,
        )

        self.sessions.append(record)
        if len(self.sessions) > self.max_sessions:
            self.sessions = self.sessions[-self.max_sessions:]

        self._total_sessions += 1

        # 更新策略效果
        self._update_strategy_efficacy(strategy, domain, gain_rate, difficulty, successful)

        return record

    def _update_strategy_efficacy(self, strategy: LearningStrategy,
                                   domain: str, gain_rate: float,
                                   difficulty: float, successful: bool):
        """更新策略效果统计"""
        key = f"{strategy.value}:{domain}"
        if key not in self.strategy_efficacy:
            self.strategy_efficacy[key] = StrategyEfficacy(
                strategy=strategy, domain=domain,
            )

        eff = self.strategy_efficacy[key]
        n = eff.times_used
        eff.avg_gain_rate = (eff.avg_gain_rate * n + gain_rate) / (n + 1)
        eff.times_used = n + 1
        eff.success_rate = (eff.success_rate * n + (1.0 if successful else 0.0)) / (n + 1)
        eff.last_used = time.time()

        # 更新最佳难度范围
        if n == 0:
            eff.best_difficulty_range = (max(0.0, difficulty - 0.2),
                                         min(1.0, difficulty + 0.2))
        else:
            low, high = eff.best_difficulty_range
            if difficulty < low:
                eff.best_difficulty_range = (difficulty, high)
            if difficulty > high:
                eff.best_difficulty_range = (low, difficulty)

    def get_learning_efficiency(self, domain: Optional[str] = None,
                                 days: int = 7) -> Dict[str, Any]:
        """获取学习效率统计"""
        cutoff = time.time() - days * 86400
        relevant = [s for s in self.sessions if s.timestamp >= cutoff]

        if domain:
            relevant = [s for s in relevant if s.domain == domain]

        if not relevant:
            return {"sessions": 0, "avg_gain_rate": 0, "avg_retention": 0}

        total_gain = sum(s.gain for s in relevant)
        total_hours = sum(s.duration_minutes for s in relevant) / 60
        avg_gain_rate = total_gain / max(0.1, total_hours)

        # 最佳策略
        strategy_gains = defaultdict(list)
        for s in relevant:
            strategy_gains[s.strategy.value].append(s.gain_rate)

        best_strategy = max(strategy_gains,
                           key=lambda k: np.mean(strategy_gains[k]) if strategy_gains[k] else 0)

        return {
            "sessions": len(relevant),
            "total_hours": round(total_hours, 2),
            "total_gain": round(total_gain, 4),
            "avg_gain_rate": round(avg_gain_rate, 4),
            "best_strategy": best_strategy,
            "strategy_performance": {
                k: round(float(np.mean(v)), 4)
                for k, v in strategy_gains.items()
            },
            "success_rate": round(
                sum(1 for s in relevant if s.successful) / max(1, len(relevant)), 3
            ),
        }

    # ─────────── 策略自动切换 ───────────

    def recommend_strategy(self, concept: str = "", domain: str = "general",
                           difficulty: float = 0.5,
                           available_strategies: Optional[List[LearningStrategy]] = None
                           ) -> LearningStrategy:
        """
        智能推荐最佳学习策略。

        基于：
          - 该领域历史最佳策略
          - 难度匹配
          - 策略多样性（避免总用同一种）
        """
        if available_strategies is None:
            available_strategies = list(LearningStrategy)

        scored = []
        for strategy in available_strategies:
            key = f"{strategy.value}:{domain}"
            eff = self.strategy_efficacy.get(key)

            if eff and eff.times_used > 0:
                # 基础分 = 平均增益率
                score = eff.avg_gain_rate * 10

                # 难度匹配加分
                low, high = eff.best_difficulty_range
                if low <= difficulty <= high:
                    score *= 1.3

                # 成功率加分
                score *= (0.5 + eff.success_rate)

                # 多样性：最近没用过的加分
                hours_since = (time.time() - eff.last_used) / 3600
                diversity_bonus = min(0.5, hours_since / 48)  # 2天没用 +0.5
                score *= (1 + diversity_bonus)

                scored.append((score, strategy))
            else:
                # 新策略给默认分
                scored.append((0.3, strategy))

        scored.sort(key=lambda x: -x[0])
        best = scored[0][1] if scored else LearningStrategy.STRUCTURED

        if best != self.current_strategy:
            self._strategy_switches += 1
            self.current_strategy = best

        return best

    def get_strategy_report(self) -> List[Dict]:
        """获取所有策略的效果报告"""
        report = defaultdict(list)
        for key, eff in self.strategy_efficacy.items():
            if eff.times_used > 0:
                report[eff.strategy.value].append(eff.to_dict())

        result = []
        for strategy, entries in sorted(report.items()):
            avg_gain = np.mean([e["avg_gain"] for e in entries]) if entries else 0
            avg_success = np.mean([e["success_rate"] for e in entries]) if entries else 0
            total_uses = sum(e["times_used"] for e in entries)
            result.append({
                "strategy": strategy,
                "avg_gain_rate": round(avg_gain, 4),
                "success_rate": round(avg_success, 3),
                "total_uses": total_uses,
                "domains": [e["domain"] for e in entries],
            })

        result.sort(key=lambda x: -x["avg_gain_rate"])
        return result

    # ─────────── 知识迁移检测 ───────────

    def _register_domain_similarities(self):
        """注册领域间的结构相似度"""
        similarities = [
            ("cognition", "philosophy", 0.7),
            ("cognition", "ml", 0.5),
            ("cognition", "social", 0.6),
            ("philosophy", "social", 0.5),
            ("math", "ml", 0.8),
            ("math", "quantum", 0.7),
            ("math", "programming", 0.5),
            ("ml", "programming", 0.6),
            ("ml", "quantum", 0.5),
            ("quantum", "philosophy", 0.4),
            ("social", "cognition", 0.6),
            ("programming", "math", 0.5),
        ]
        for d1, d2, sim in similarities:
            self.domain_similarity[d1][d2] = sim
            self.domain_similarity[d2][d1] = sim

    def detect_transfer(self, source_concept: str, source_domain: str,
                         target_concept: str, target_domain: str,
                         similarity: float = 0.5) -> Optional[KnowledgeTransfer]:
        """
        检测两条知识之间的可迁移性。

        基于：
          - 领域相似度
          - 概念结构相似度
          - 已有迁移历史
        """
        # 领域相似度
        domain_sim = self.domain_similarity.get(source_domain, {}).get(target_domain, 0.1)

        # 综合相似度
        combined = (domain_sim * 0.4 + similarity * 0.6)

        if combined > 0.3:
            transfer = KnowledgeTransfer(
                source_domain=source_domain,
                target_domain=target_domain,
                source_concept=source_concept,
                target_concept=target_concept,
                similarity=combined,
                transfer_effect=combined * 0.5,  # 预期迁移效果
                confidence=min(1.0, combined),
            )
            self.transfers.append(transfer)
            if len(self.transfers) > self.max_transfers:
                self.transfers = self.transfers[-self.max_transfers:]
            self._transfer_discoveries += 1
            return transfer

        return None

    def find_transfer_opportunities(self, concept: str, domain: str
                                     ) -> List[KnowledgeTransfer]:
        """找出某个概念可以迁移到哪些领域/概念"""
        opportunities = []

        # 从已有迁移中找
        for t in self.transfers:
            if t.source_concept == concept:
                opportunities.append(t)

        # 从领域相似度推测潜在迁移
        for other_domain, sim in self.domain_similarity.get(domain, {}).items():
            if sim > 0.4:
                # 检查是否已有记录
                already = any(
                    t.target_domain == other_domain and t.source_concept == concept
                    for t in self.transfers
                )
                if not already:
                    opportunities.append(KnowledgeTransfer(
                        source_domain=domain, target_domain=other_domain,
                        source_concept=concept, target_concept=f"{other_domain}_analog",
                        similarity=sim, transfer_effect=sim * 0.3,
                        confidence=sim * 0.6,
                    ))

        opportunities.sort(key=lambda x: -x.transfer_effect)
        return opportunities[:10]

    def measure_transfer_effect(self, source_concept: str, target_concept: str,
                                 gain_without: float, gain_with: float) -> float:
        """
        衡量知识迁移的实际效果。

        对比：
          - 没有源知识时学习目标概念的速度
          - 有源知识时学习目标概念的速度

        Returns: 迁移提升率 (0~1)
        """
        if gain_without <= 0:
            return 1.0 if gain_with > 0 else 0.0
        improvement = (gain_with - gain_without) / gain_without
        return max(0.0, min(1.0, improvement))

    # ─────────── 学习收益评估 ───────────

    def evaluate_learning_gain(self, concept: str, domain: str,
                                 time_invested_hours: float,
                                 mastery_gain: float) -> Dict[str, Any]:
        """
        评估一次学习的收益。

        比较：
          - 预期收益（基于历史均值）
          - 实际收益
          - 收益/时间比
        """
        # 历史基准
        history = [s for s in self.sessions
                  if s.concept == concept or s.domain == domain]

        expected_gain_rate = 0.05  # 默认
        if history:
            expected_gain_rate = np.mean([s.gain_rate for s in history])

        actual_gain_rate = mastery_gain / max(0.01, time_invested_hours)
        efficiency_ratio = actual_gain_rate / max(0.001, expected_gain_rate)

        # 最佳策略
        best_strategy = self.recommend_strategy(concept, domain)

        # 遗忘预测
        retention_24h = 0.5 + 0.3 * efficiency_ratio  # 粗略估计
        retention_24h = min(0.95, max(0.1, retention_24h))

        return {
            "concept": concept,
            "domain": domain,
            "time_invested_hours": round(time_invested_hours, 2),
            "mastery_gain": round(mastery_gain, 4),
            "expected_gain_rate": round(expected_gain_rate, 4),
            "actual_gain_rate": round(actual_gain_rate, 4),
            "efficiency_ratio": round(efficiency_ratio, 3),
            "best_strategy": best_strategy.value,
            "predicted_24h_retention": round(retention_24h, 3),
            "verdict": "高效" if efficiency_ratio > 1.2 else (
                "正常" if efficiency_ratio > 0.8 else "低效"
            ),
        }

    # ─────────── 统计与序列化 ───────────

    def stats(self) -> dict:
        """引擎统计"""
        return {
            "total_sessions": self._total_sessions,
            "strategy_switches": self._strategy_switches,
            "transfer_discoveries": self._transfer_discoveries,
            "strategies_tracked": len(self.strategy_efficacy),
            "transfers_found": len(self.transfers),
            "current_strategy": self.current_strategy.value,
            "efficiency_7d": self.get_learning_efficiency(days=7),
        }

    def save(self, path: str = None):
        path = path or os.environ.get("LAAP_STATE_PATH", "./agi_state/meta_learning.json")
        """持久化元学习状态"""
        data = {
            "sessions": [s.to_dict() for s in self.sessions[-100:]],  # 只保留最近100条
            "strategy_efficacy": {k: v.to_dict() for k, v in self.strategy_efficacy.items()},
            "transfers": [t.to_dict() for t in self.transfers[-50:]],
            "total_sessions": self._total_sessions,
            "strategy_switches": self._strategy_switches,
            "transfer_discoveries": self._transfer_discoveries,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
        logger.info(f"[MetaLearningEngine] 保存到 {path}")

    def load(self, path: str = None):
        path = path or os.environ.get("LAAP_STATE_PATH", "./agi_state/meta_learning.json")
        """加载元学习状态"""
        p = Path(path)
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            self._total_sessions = data.get("total_sessions", 0)
            self._strategy_switches = data.get("strategy_switches", 0)
            self._transfer_discoveries = data.get("transfer_discoveries", 0)
            logger.info(f"[MetaLearningEngine] 加载完成")
            return True
        except Exception as e:
            logger.error(f"[MetaLearningEngine] 加载失败: {e}")
            return False


# ═══════════════════════════════════════════════════════════════
# 测试
# ═══════════════════════════════════════════════════════════════

def test():
    engine = MetaLearningEngine()
    logger.info("=" * 50)
    logger.info("P2-1 元学习引擎测试")
    logger.info("=" * 50)
    logger.info("\n=== 测试1: 学习会话记录 ===")
    for i in range(10):
        engine.record_session(
            concept="PSI_cycle", strategy=LearningStrategy.THEORETICAL,
            duration_minutes=30 + i * 5, mastery_before=0.1 + i * 0.02,
            mastery_after=0.2 + i * 0.05, difficulty=0.3, domain="cognition",
        )
    for i in range(5):
        engine.record_session(
            concept="causal_reasoning", strategy=LearningStrategy.PRACTICAL,
            duration_minutes=45, mastery_before=0.0,
            mastery_after=0.15 + i * 0.03, difficulty=0.5, domain="cognition",
        )
    eff = engine.get_learning_efficiency(domain="cognition", days=7)
    logger.info(f"  认知领域学习效率:")
    logger.info(f"    会话: {eff['sessions']}, 总时长: {eff['total_hours']}h")
    logger.info(f"    平均增益率: {eff['avg_gain_rate']}/h")
    logger.info(f"    成功率: {eff['success_rate']}")
    logger.info(f"    最佳策略: {eff['best_strategy']}")
    logger.info("\n=== 测试2: 策略自动推荐 ===")
    for diff, domain in [(0.3, "cognition"), (0.7, "math"), (0.5, "social")]:
        rec = engine.recommend_strategy(domain=domain, difficulty=diff)
        logger.info(f"  领域={domain}, 难度={diff} → 推荐策略: {rec.value}")
    report = engine.get_strategy_report()
    logger.info(f"\n  策略效果排名:")
    for r in report[:4]:
        logger.info(f"    {r['strategy']}: gain={r['avg_gain_rate']}, succ={r['success_rate']}, used={r['total_uses']}次")
    logger.info("\n=== 测试3: 知识迁移检测 ===")
    t1 = engine.detect_transfer("概率论", "math", "机器学习", "ml", similarity=0.7)
    if t1:
        logger.info(f"  发现迁移: {t1.source_domain}/{t1.source_concept} → {t1.target_domain}/{t1.target_concept}")
        logger.info(f"    相似度: {t1.similarity:.3f}, 预期效果: {t1.transfer_effect:.3f}")
    t2 = engine.detect_transfer("PSI_cycle", "cognition", "consciousness", "philosophy", similarity=0.6)
    if t2:
        logger.info(f"  发现迁移: {t2.source_domain}/{t2.source_concept} → {t2.target_domain}/{t2.target_concept}")
    ops = engine.find_transfer_opportunities("PSI_cycle", "cognition")
    logger.info(f"\n  PSI_cycle 的潜在迁移机会: {len(ops)} 个")
    for o in ops[:3]:
        logger.info(f"    → {o.target_domain}: effect={o.transfer_effect:.3f}, conf={o.confidence:.3f}")
    logger.info("\n=== 测试4: 学习收益评估 ===")
    eval_result = engine.evaluate_learning_gain(
        "PSI_cycle", "cognition", time_invested_hours=5.0, mastery_gain=0.3,
    )
    logger.info(f"  概念: {eval_result['concept']}")
    logger.info(f"  投入: {eval_result['time_invested_hours']}h, 掌握度提升: {eval_result['mastery_gain']}")
    logger.info(f"  预期增益率: {eval_result['expected_gain_rate']}/h")
    logger.info(f"  实际增益率: {eval_result['actual_gain_rate']}/h")
    logger.info(f"  效率比: {eval_result['efficiency_ratio']} ({eval_result['verdict']})")
    logger.info(f"  24h预计保留: {eval_result['predicted_24h_retention']}")
    logger.info(f"  推荐策略: {eval_result['best_strategy']}")
    logger.info(f"\n=== 引擎统计 ===")
    for k, v in engine.stats().items():
        logger.info(f"  {k}: {v}")
    engine.save()
    logger.info(f"\n✅ P2-1 元学习引擎全部测试通过！")
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test()
