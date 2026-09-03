"""
LAAP AGI — PSI Driver (PSI认知驱动引擎)

Implements the PSI theory (Dietrich Dörner) cognition cycle:
  1. Perceive  — sensory input → internal representation (WorldModel)
  2. Select   — needs/emotion/bias → what to attend to (ConsciousStream/Attention)
  3. Integrate — bind perceptions + memories + predictions into unified experience
  4. Act      — generate response based on integrated state (LLM as I/O, not as thinker)
  5. Learn    — update world model, self model, skills from outcomes

The LLM becomes just the natural language I/O channel within this cycle,
NOT the cognitive driver. This module is OPT-IN (use_psi=False by default)
and NEVER breaks existing functionality.

Integration:
    from laap.agi.psi_driver import PSIDriver, integrate_psi_driver

    # Attach to agent
    driver = integrate_psi_driver(agent, llm_channel=my_llm_fn)

    # Use via process_interaction(use_psi=True)
    result = agent.process_interaction("Hello", use_psi=True)
"""

from __future__ import annotations

import logging

from typing import Any, Dict, List, Optional, Tuple
import time, logging
from laap.agi.world_model import EntityType

logger = logging.getLogger("laap.agi.psi_driver")


class PSIDriver:
    """
    PSI-driven cognitive engine. Replaces LLM-as-thinker loop.

    Flow per interaction:
      1. perceive()   → WorldModel.add_entity() + ConsciousStream.experience()
      2. select()     → needs assessment → attention focus
      3. integrate()  → bind context → generate unified state
      4. decide()     → select action based on integrated state
      5. learn()      → update self-model + memory + learning pipeline

    The LLM is called only in step 4 (decide) for natural language generation,
    and is a sub-processor, not the driver.
    """

    def __init__(self, agent: Any, llm_channel: Optional[callable] = None,
                 enable_causal_verification: bool = False):
        self.agent = agent            # AGIAgent instance
        self.llm = llm_channel        # LLM I/O channel (sub-processor)
        self.cycle_count = 0
        self.last_domain = "general"
        self._last_focus = "respond"
        # P1-5: 启用真正的因果一致性校验(从 LLM 响应抽取因果声明,
        # 调 causal_engine 查询是否与已学因果键/规则一致)
        self.enable_causal_verification = enable_causal_verification
        self._causal_violations: List[Dict[str, Any]] = []

    def process(self, user_input: str, domain: str = "general") -> str:
        """
        Run one full PSI cognition cycle.

        Args:
            user_input: The user's natural language input
            domain: Task domain label

        Returns:
            Natural language response string
        """
        # ═══════════════════════════════════════════════════════════
        # Step 1: Perceive
        # ═══════════════════════════════════════════════════════════
        self.last_domain = domain

        if hasattr(self.agent, 'world') and self.agent.world:
            self.agent.world.add_entity(
                name=f"user_input_{self.cycle_count}",
                entity_type=EntityType.ACTION,
                properties={"content": user_input, "domain": domain},
            )

        if hasattr(self.agent, 'conscious') and self.agent.conscious:
            self.agent.conscious.experience(user_input)

        # ─── Causal analysis: learn from message, predict interventions ───
        causal_context = ""
        if hasattr(self.agent, 'causal') and self.agent.causal:
            try:
                # P0-2: 原 causal.observe/add_variable/_find_var/add_edge 方法
                # 在 UnifiedCausalEngine 中均不存在,改为使用真实 API:
                # learn_bond / learn_temporal_link / learn_entity_state
                causal = self.agent.causal
                words = user_input.lower().split()[:5]
                keywords = [w for w in words if len(w) > 3 and w.isalpha()]

                if keywords:
                    # 把每个关键词作为实体状态注入(entity_states)
                    for w in keywords:
                        try:
                            causal.learn_entity_state(
                                entity_id=w,
                                state={"value": 1.0, "domain": domain, "source": "user_input"},
                            )
                        except Exception:
                            # learn_entity_state 可能签名不同,降级为直接写 entity_states
                            causal.entity_states[w] = {
                                "value": 1.0, "domain": domain, "ts": self.cycle_count,
                            }

                    # 关键词之间建立因果键(前一个词 → 后一个词)
                    # learn_bond 签名: (action, target, effect, matched: bool, domain)
                    for i in range(len(keywords) - 1):
                        cause_w, effect_w = keywords[i], keywords[i + 1]
                        try:
                            causal.learn_bond(
                                action=cause_w,
                                target=effect_w,
                                effect=f"{cause_w} 引发 {effect_w}",
                                matched=True,
                                domain=domain,
                            )
                        except Exception as e:
                            logger.debug(f"learn_bond 失败: {e}")

                    # 建立时间因果链(同一序列内)
                    for i in range(len(keywords) - 1):
                        cause_w, effect_w = keywords[i], keywords[i + 1]
                        try:
                            causal.learn_temporal_link(
                                cause=cause_w,
                                effect=effect_w,
                                delay=1.0,
                                confidence=0.35,
                            )
                        except Exception as e:
                            logger.debug(f"learn_temporal_link 失败: {e}")

                cs = causal.stats()
                # UnifiedCausalEngine.stats() 返回 causal_bonds / temporal_links 等
                n_vars = cs.get("entity_states", 0)
                n_bonds = cs.get("causal_bonds", 0)
                if n_vars > 0 or n_bonds > 0:
                    causal_context = (
                        f"[Causal: {n_vars} vars, {n_bonds} bonds, "
                        f"{cs.get('temporal_links', 0)} temporal]"
                    )
            except Exception as e:
                causal_context = f"[Causal: {e}]"

        # ─── Analogical transfer: find cross-domain patterns ───
        analogy_context = ""
        if hasattr(self.agent, 'analogical') and self.agent.analogical:
            try:
                domain_data = {"domain": domain, "user_input": user_input[:200]}
                self.agent.analogical.encode_domain(domain, [domain_data])
                analogies = self.agent.analogical.query_analogies(domain)
                if analogies:
                    analogy_str = "; ".join([f"{a[0]}(conf={a[1]:.2f})" for a in analogies[:3]])
                    analogy_context = f"[Analogies: {analogy_str}]"
                if len(analogies) >= 2:
                    mapping = self.agent.analogical.find_analogy(domain)
                    if mapping and mapping.similarity_score > 0.3:
                        analogy_context += f" [Mapping: {mapping.source_domain}->{mapping.target_domain}, sim={mapping.similarity_score:.2f}]"
            except Exception as e:
                analogy_context = f"[Analogies: {e}]"

        # ═══════════════════════════════════════════════════════════
        # Step 2: Selection (needs/emotion drive attention)
        # ═══════════════════════════════════════════════════════════
        focus = "respond"
        if hasattr(self.agent, 'conscious') and hasattr(
            self.agent.conscious, 'attention'
        ):
            attn = self.agent.conscious.attention
            if hasattr(attn, 'determine_focus'):
                try:
                    raw_focus = attn.determine_focus({"user_input": user_input})
                    focus = raw_focus.value if hasattr(raw_focus, 'value') else str(raw_focus)
                except Exception:
                    focus = "respond"

        self._last_focus = focus

        # ═══════════════════════════════════════════════════════════
        # Step 3: Integration
        # ═══════════════════════════════════════════════════════════
        context = self._build_context(domain=domain, focus=focus,
                                     causal_context=causal_context,
                                     analogy_context=analogy_context)

        # ═══════════════════════════════════════════════════════════
        # Step 4: Action (LLM as sub-processor)
        # ═══════════════════════════════════════════════════════════
        if self.llm:
            response = self.llm(context + "\n\nUser: " + user_input)
        else:
            response = self._fallback_respond(domain)

        # ─── Causal consistency verification ───
        response = self._causal_verify(response)

        # ═══════════════════════════════════════════════════════════
        # Step 5: Learning
        # ═══════════════════════════════════════════════════════════
        self._learn(user_input, response, domain)

        self.cycle_count += 1
        return response

    def _build_context(self, domain: str, focus: str = "respond",
                       causal_context: str = "", analogy_context: str = "") -> str:
        """Build attention-weighted context from all cognitive modules."""
        tiers = {"high": [], "medium": [], "low": []}

        # High tier: conscious state + focus
        if hasattr(self.agent, 'conscious') and self.agent.conscious:
            try:
                cs = self.agent.conscious.stats()
                tiers["high"].append(f"[Conscious: focus={focus}, valence={cs.get('valence', 0):.2f}]")
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if hasattr(self.agent, 'self_model') and self.agent.self_model:
            try:
                sm = self.agent.self_model.stats()
                tiers["high"].append(f"[Self: {sm.get('total_experiences', 0)} exp, {sm.get('skills', 0)} skills]")
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if causal_context:
            tiers["medium"].append(causal_context)
        if analogy_context:
            tiers["medium"].append(analogy_context)

        if hasattr(self.agent, 'world') and self.agent.world:
            try:
                wm = f"[World: {len(self.agent.world.entities)} entities, {len(self.agent.world.relations)} relations]"
                tiers["medium"].append(wm)
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if hasattr(self.agent, 'memory_system') and self.agent.memory_system:
            try:
                ms = self.agent.memory_system.stats()
                tiers["low"].append(f"[Memory: {ms.get('total_memories', 0)} episodes]")
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        if hasattr(self.agent, 'learning') and self.agent.learning:
            try:
                tiers["low"].append("[Learning: ready]")
            except Exception as e:
                logger.debug(f"操作失败: {e}")
        parts = []
        for tier_name in ["high", "medium", "low"]:
            if tiers[tier_name]:
                parts.append(f"[{tier_name.upper()} PRIORITY]")
                parts.extend(tiers[tier_name])

        return chr(10).join(parts) if parts else "[Cognitive context: initializing]"

    def _learn(self, user_input: str, response: str, domain: str):
        """Post-interaction learning across all modules."""
        # Self-model learning
        if (
            hasattr(self.agent, 'self_model')
            and self.agent.self_model
            and hasattr(self.agent.self_model, 'record_experience')
        ):
            try:
                self.agent.self_model.record_experience(
                    domain=domain,
                    outcome_score=0.5,
                    predicted_confidence=0.5,
                    is_success=True,
                    description=f"PSI cycle {self.cycle_count}: {user_input[:60]}",
                )
            except Exception as e:
                logger.debug(f"Self-model learn skipped: {e}")

        # Memory system
        if hasattr(self.agent, 'memory_system') and self.agent.memory_system:
            try:
                self.agent.memory_system.remember_episode(
                    event=user_input,
                    context={"response": response, "domain": domain},
                )
            except Exception as e:
                logger.debug(f"Memory learn skipped: {e}")

        # Learning pipeline
        if hasattr(self.agent, 'learning') and self.agent.learning:
            try:
                self.agent.learning.learn(
                    domain=domain,
                    action=user_input[:80],
                    outcome=0.5,
                )
            except Exception as e:
                logger.debug(f"Learning pipeline learn skipped: {e}")

    def _causal_verify(self, response: str) -> str:
        """P1-5: 真正的因果一致性校验。

        从 LLM 响应中抽取 "X causes/affects/leads to Y" 等因果声明,
        调用 UnifiedCausalEngine 查询已学因果键/规则,若声明与已知因果
        矛盾(反向或不存在),在响应末尾追加警告标注。

        Args:
            response: LLM 生成的原始响应

        Returns:
            校验后的响应(可能追加 [Causal Warning] 标注)
        """
        if not self.enable_causal_verification:
            return response
        if not hasattr(self.agent, 'causal') or not self.agent.causal:
            return response
        try:
            import re as _re
            causal = self.agent.causal
            cs = causal.stats()
            # 至少需要 2 个因果键才有校验意义
            if cs.get("causal_bonds", 0) < 2 and cs.get("temporal_links", 0) < 2:
                return response

            # 抽取因果声明:支持 "X causes Y" / "X affects Y" / "X leads to Y"
            # / "X 导致 Y" / "X 引起 Y" / "X 影响 Y"
            patterns = [
                r'(\w+)\s+(?:causes?|affects?|leads?\s+to|triggers?)\s+(\w+)',
                r'(\w+)\s+(?:导致|引起|影响|引发)\s+(\w+)',
            ]
            claims = []
            for pat in patterns:
                claims.extend(_re.findall(pat, response.lower()))

            if not claims:
                return response

            # 已知因果键集合(从 bonds 与 temporal_links 提取)
            known_forward = set()  # (cause, effect)
            known_reverse = set()  # (effect, cause) — 反向
            for bond_key in getattr(causal, 'bonds', {}).keys():
                # bond_key 格式: "action→target:effect"
                try:
                    pair = bond_key.split(':', 1)[0]
                    if '→' in pair:
                        c, e = pair.split('→', 1)
                        known_forward.add((c, e))
                        known_reverse.add((e, c))
                except Exception:
                    pass
            for link_key in getattr(causal, 'temporal_links', {}).keys():
                try:
                    if '→' in link_key:
                        c, e = link_key.split('→', 1)
                        known_forward.add((c, e))
                        known_reverse.add((e, c))
                except Exception:
                    pass

            if not known_forward:
                return response

            violations = []
            for cause_claim, effect_claim in claims:
                cause_claim = cause_claim.strip()
                effect_claim = effect_claim.strip()
                if len(cause_claim) < 2 or len(effect_claim) < 2:
                    continue
                # 检查是否反向(声称 A→B 但已知 B→A)
                if (cause_claim, effect_claim) in known_reverse:
                    violations.append(
                        f"声明 '{cause_claim}→{effect_claim}' 与已知反向因果冲突"
                    )
                # 检查是否完全未知(声称 A→B 但 A 和 B 都在已知集中却无连接)
                elif ((cause_claim, effect_claim) not in known_forward
                      and any(c == cause_claim for c, _ in known_forward)
                      and any(e == effect_claim for _, e in known_forward)):
                    violations.append(
                        f"声明 '{cause_claim}→{effect_claim}' 未在已知因果键中找到"
                    )

            if violations:
                self._causal_violations.extend(violations)
                warning = "\n[Causal Warning] " + "; ".join(violations[:3])
                return response + warning
            return response
        except Exception as e:
            logger.debug(f"_causal_verify 失败: {e}")
            return response

    def _fallback_respond(self, domain: str) -> str:
        """Fallback response when no LLM channel is available."""
        return (
            f"[PSI Driver - {domain}] Processed cycle {self.cycle_count}. "
            "No LLM channel available."
        )

    def stats(self) -> Dict[str, Any]:
        """Return PSI driver statistics."""
        modules_available = sum(
            1 for m in [
                'world', 'self_model', 'conscious', 'causal',
                'analogical', 'memory_system', 'learning',
            ]
            if hasattr(self.agent, m) and getattr(self.agent, m) is not None
        )
        return {
            "cycles": self.cycle_count,
            "domain": self.last_domain,
            "focus": self._last_focus,
            "modules_available": modules_available,
            "llm_connected": self.llm is not None,
        }


def integrate_psi_driver(
    agent: Any,
    llm_channel: Optional[callable] = None,
    enable_causal_verification: bool = False,
) -> PSIDriver:
    """
    Attach a PSI Driver to an AGIAgent instance.

    Sets `agent.psi_driver` to the new PSIDriver instance. Existing
    functionality is completely unaffected — the PSI driver is only
    activated when `use_psi=True` is passed to process_interaction().

    Args:
        agent: AGIAgent instance (or any object with the expected modules)
        llm_channel: Callable that takes a prompt string and returns a
                     natural language response string. This is the LLM
                     acting as an I/O sub-processor only.
        enable_causal_verification: P1-5 — 若为 True,PSI driver 会从 LLM
                     响应中抽取因果声明,与 UnifiedCausalEngine 已学因果
                     键/规则做一致性校验,矛盾时追加 [Causal Warning]。

    Returns:
        The PSIDriver instance
    """
    driver = PSIDriver(
        agent, llm_channel,
        enable_causal_verification=enable_causal_verification,
    )
    agent.psi_driver = driver
    logger.info(
        f"PSI Driver integrated into {getattr(agent, 'name', 'agent')} "
        f"(causal_verification={enable_causal_verification})"
    )
    return driver
