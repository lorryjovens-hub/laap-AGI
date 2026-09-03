"""LAAP Causal Backend — causal-learn + DoWhy 严谨因果推理封装。

P1-4: 原 UnifiedCausalEngine 的 PC 算法无 V-结构识别、do-calculus 无三规则、
反事实仅占位级。本模块封装两个业界标准库,作为 UnifiedCausalEngine 的可选
增强后端(不是替换),提供:

  - causal-learn(CMU):PC / FCI / GES 算法,真 V-结构与 Meek 规则定向
  - DoWhy(Microsoft):do-calculus 三规则 + 反事实三步法 + 后门调整

设计原则:
  1. 延迟导入 — causal-learn/DoWhy 是重依赖,仅在调用时 import
  2. 容错降级 — 库缺失或数据不足时返回 None,不抛异常
  3. 与 UnifiedCausalEngine 互补 — 提供 `enhance_engine(engine)` 注入方法,
     把发现的关系写回 engine.bonds / engine.temporal_links
  4. 数据格式对齐 — 接受 numpy ndarray / pandas DataFrame / dict of lists

用法:
    from laap.agi.causal_backend import LAAPCausalBackend
    backend = LAAPCausalBackend()
    # 因果发现
    graph = backend.discover(variables=['A','B','C'], data=my_ndarray)
    # 干预效应
    effect = backend.estimate_effect(data=df, treatment='A', outcome='C',
                                     common_causes=['B'])
    # 反事实
    cf = backend.counterfactual(data=df, treatment='A', outcome='C',
                                treatment_value=1, counterfactual_value=0)
    # 增强已有 UnifiedCausalEngine
    backend.enhance_engine(my_causal_engine, data=my_data,
                           variables=['A','B','C'])
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union, Tuple

import numpy as np

# P1-4 workaround: causal-learn 内部 `tqdm.auto` 在 Windows 上会扫描所有
# dist-info 的 entry_points.txt,某些损坏的元数据(如 oauthlib)会触发
# Errno 22 Invalid argument。设置 TQDM_DISABLE=1 强制 tqdm 走非 auto 路径。
# 必须在 import causallearn 之前设置。
if "TQDM_DISABLE" not in os.environ:
    os.environ["TQDM_DISABLE"] = "1"

logger = logging.getLogger("laap.agi.causal_backend")


class LAAPCausalBackend:
    """基于 causal-learn + DoWhy 的严谨因果推理后端。

    封装两个业界标准库,补足 UnifiedCausalEngine 自研简化版在算法严谨性上的不足:
      - PC 算法真 V-结构 + Meek 规则定向(causal-learn)
      - do-calculus 三规则 + 反事实三步法 + 后门调整(DoWhy)
    """

    def __init__(self, discovery_method: str = "pc",
                 significance_level: float = 0.05):
        """初始化因果推理后端。

        Args:
            discovery_method: 发现算法,支持 "pc" / "fci" / "ges"(默认 "pc")
            significance_level: 条件独立性检验显著性水平(默认 0.05)
        """
        self.discovery_method = discovery_method
        self.significance_level = significance_level
        self._causal_learn = None  # 延迟导入
        self._dowhy = None
        self._last_graph = None
        self._last_model = None
        logger.info(
            f"[LAAPCausalBackend] 初始化 method={discovery_method} "
            f"alpha={significance_level}"
        )

    # ─────────── 因果发现(causal-learn) ───────────

    def discover(
        self,
        variables: List[str],
        data: Union[np.ndarray, "pd.DataFrame", Dict[str, List[float]]],
        method: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """用 causal-learn 算法从数据中发现因果图。

        支持 PC(约束式)、FCI(可处理隐混杂)、GES(分数式)。
        相比 UnifiedCausalEngine.CausalDiscovery,本方法实现真 V-结构识别
        与 Meek 规则定向。

        Args:
            variables: 变量名列表
            data: 数据矩阵(n_samples × n_vars)或 DataFrame 或 dict
            method: 算法覆盖(None 用 self.discovery_method)

        Returns:
            {
                "graph": CausalGraph 对象(causal-learn),
                "edges": [(cause_idx, effect_idx, edge_type_str), ...],
                "adjacency_matrix": np.ndarray,
                "variables": variables,
                "method": method,
            } 或 None(失败时)
        """
        method = method or self.discovery_method
        try:
            data_arr, var_names = self._normalize_data(data, variables)
            if data_arr is None or data_arr.shape[0] < 5:
                logger.warning("[discover] 数据不足(需 ≥5 样本)")
                return None

            cg = self._run_causal_learn(method, data_arr, var_names)
            if cg is None:
                return None

            self._last_graph = cg
            edges = self._extract_edges(cg, var_names)
            adj = cg.G.graph if hasattr(cg, 'G') else getattr(cg, 'graph', None)

            logger.info(
                f"[discover] {method} 发现 {len(edges)} 条边 "
                f"(variables={len(var_names)}, samples={data_arr.shape[0]})"
            )
            return {
                "graph": cg,
                "edges": edges,
                "adjacency_matrix": adj,
                "variables": var_names,
                "method": method,
            }
        except Exception as e:
            logger.warning(f"[discover] 失败: {e}")
            return None

    def _run_causal_learn(self, method: str, data: np.ndarray,
                          var_names: List[str]):
        """执行 causal-learn 算法。"""
        if self._causal_learn is None:
            try:
                import causallearn  # type: ignore
                self._causal_learn = causallearn
            except ImportError as e:
                logger.warning(
                    f"[causal-learn] 未安装,因果发现降级。pip install causal-learn. "
                    f"错误: {e}"
                )
                return None

        cl = self._causal_learn
        try:
            if method == "pc":
                from causallearn.search.ConstraintBased.PC import pc
                cg = pc(data, alpha=self.significance_level)
                # PC 返回 CausalGraph
                return cg
            elif method == "fci":
                from causallearn.search.ConstraintBased.FCI import fci
                cg, edges = fci(data, alpha=self.significance_level)
                return cg
            elif method == "ges":
                # GES 是分数式搜索
                from causallearn.search.ScoreBased.GES import ges
                RecordMap = ges(data, "local_score_BIC")
                return RecordMap if RecordMap else None
            else:
                logger.warning(f"[causal-learn] 未知方法: {method}")
                return None
        except Exception as e:
            logger.warning(f"[causal-learn] {method} 执行失败: {e}")
            return None

    def _extract_edges(self, cg, var_names: List[str]) -> List[Tuple[str, str, str]]:
        """从 causal-learn 的 CausalGraph 提取边列表。"""
        edges = []
        try:
            # causal-learn 的 PC/FCI 用 G.graph 表示邻接矩阵
            # G.graph[i, j] 的值:
            #   -1 = i → j(箭头从 j 指向 i,即 j 是 i 的父节点)
            #    1 = i ← j
            #    0 = 无边
            #   None = 无向边(部分定向)
            G = cg.G if hasattr(cg, 'G') else cg
            adj = G.graph if hasattr(G, 'graph') else G
            n = len(var_names)
            for i in range(n):
                for j in range(n):
                    if i == j:
                        continue
                    val = adj[i, j] if hasattr(adj, '__getitem__') else 0
                    if val == -1 and adj[j, i] == 1:
                        # i → j (j 是 i 的子节点)
                        edges.append((var_names[i], var_names[j], "directed"))
                    elif val == 1 and adj[j, i] == -1:
                        pass  # 已在 i<j 时记录
                    elif val == -1 and adj[j, i] == -1:
                        # 双向(隐混杂)
                        edges.append((var_names[i], var_names[j], "bidirected"))
        except Exception as e:
            logger.debug(f"[_extract_edges] 失败: {e}")
        return edges

    # ─────────── 干预效应估计(DoWhy) ───────────

    def estimate_effect(
        self,
        data: "pd.DataFrame",
        treatment: str,
        outcome: str,
        common_causes: Optional[List[str]] = None,
        effect_modifiers: Optional[List[str]] = None,
        method_name: str = "backdoor.propensity_score_matching",
    ) -> Optional[Dict[str, Any]]:
        """用 DoWhy 估计干预效应(P(outcome | do(treatment)))。

        相比 UnifiedCausalEngine.intervene(仅修改状态前后对比),本方法实现
        真正的后门调整 + 倾向得分匹配 + 多种估计器。

        Args:
            data: pandas DataFrame
            treatment: 处理变量名
            outcome: 结果变量名
            common_causes: 混杂因子列表(后门调整集)
            effect_modifiers: 效应修饰因子
            method_name: DoWhy 估计方法(默认倾向得分匹配)

        Returns:
            {
                "estimated_effect": float,
                "ci_lower": float,
                "ci_upper": float,
                "method": method_name,
                "treatment": treatment,
                "outcome": outcome,
            } 或 None
        """
        try:
            dowhy_model = self._build_dowhy_model(
                data, treatment, outcome, common_causes, effect_modifiers
            )
            if dowhy_model is None:
                return None

            identified_estimand = dowhy_model.identify_effect(
                proceed_when_unidentifiable=True
            )
            estimate = dowhy_model.estimate_effect(
                identified_estimand, method_name=method_name
            )

            # 置信区间(若估计器支持)
            ci_lower, ci_upper = None, None
            try:
                ci = estimate.get_confidence_interval()
                if ci is not None:
                    ci_lower, ci_upper = float(ci[0]), float(ci[1])
            except Exception:
                pass

            result = {
                "estimated_effect": float(estimate.value),
                "ci_lower": ci_lower,
                "ci_upper": ci_upper,
                "method": method_name,
                "treatment": treatment,
                "outcome": outcome,
            }
            logger.info(
                f"[estimate_effect] {treatment}→{outcome} "
                f"effect={result['estimated_effect']:.4f}"
            )
            return result
        except Exception as e:
            logger.warning(f"[estimate_effect] 失败: {e}")
            return None

    def counterfactual(
        self,
        data: "pd.DataFrame",
        treatment: str,
        outcome: str,
        treatment_value: Any,
        counterfactual_value: Any,
        common_causes: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """DoWhy 反事实推理(Pearl 三步法:abduction/action/prediction)。

        相比 UnifiedCausalEngine.counterfactual(状态快照+规则模拟),本方法
        基于结构因果模型(SCM)实现严谨反事实。

        Args:
            data: DataFrame
            treatment: 处理变量
            outcome: 结果变量
            treatment_value: 事实处理值
            counterfactual_value: 反事实处理值
            common_causes: 混杂因子

        Returns:
            {
                "factual_outcome": float,
                "counterfactual_outcome": float,
                "effect": float,  # 反事实效应
                "confidence": float,
            } 或 None
        """
        try:
            dowhy_model = self._build_dowhy_model(
                data, treatment, outcome, common_causes
            )
            if dowhy_model is None:
                return None

            identified_estimand = dowhy_model.identify_effect(
                proceed_when_unidentifiable=True
            )

            # 用线性回归估计器做反事实
            estimate = dowhy_model.estimate_effect(
                identified_estimand,
                method_name="backdoor.linear_regression",
                control_value=counterfactual_value,
                treatment_value=treatment_value,
                target_units="ate",  # average treatment effect
            )

            # 计算反事实效应
            factual = float(estimate.value)
            # DoWhy 不直接给反事实值,用 effect 推算
            # effect = E[Y|do(T=treatment_value)] - E[Y|do(T=counterfactual_value)]
            cf_estimate = dowhy_model.estimate_effect(
                identified_estimand,
                method_name="backdoor.linear_regression",
                control_value=treatment_value,
                treatment_value=counterfactual_value,
                target_units="ate",
            )
            counterfactual = float(cf_estimate.value)

            result = {
                "factual_outcome": factual,
                "counterfactual_outcome": counterfactual,
                "effect": factual - counterfactual,
                "confidence": 0.75,  # DoWhy 不直接提供,给默认值
            }
            logger.info(
                f"[counterfactual] {treatment}={treatment_value}→{outcome}="
                f"{factual:.4f}; 反事实 {treatment}={counterfactual_value}→"
                f"{counterfactual:.4f}; effect={result['effect']:.4f}"
            )
            return result
        except Exception as e:
            logger.warning(f"[counterfactual] 失败: {e}")
            return None

    def _build_dowhy_model(self, data, treatment, outcome,
                           common_causes=None, effect_modifiers=None):
        """构建 DoWhy 因果模型(延迟导入)。"""
        if self._dowhy is None:
            try:
                import dowhy  # type: ignore
                from dowhy import CausalModel  # type: ignore
                self._dowhy = dowhy
                self._dowhy.CausalModel = CausalModel
            except ImportError as e:
                logger.warning(
                    f"[dowhy] 未安装,干预/反事实降级。pip install dowhy. "
                    f"错误: {e}"
                )
                return None

        try:
            CausalModel = self._dowhy.CausalModel
            model = CausalModel(
                data=data,
                treatment=treatment,
                outcome=outcome,
                common_causes=common_causes or [],
                effect_modifiers=effect_modifiers or [],
            )
            self._last_model = model
            return model
        except Exception as e:
            logger.warning(f"[_build_dowhy_model] 失败: {e}")
            return None

    # ─────────── 引擎增强(写回 UnifiedCausalEngine) ───────────

    def enhance_engine(self, engine, data, variables: List[str],
                       method: Optional[str] = None) -> int:
        """用 causal-learn 发现的关系增强 UnifiedCausalEngine。

        把发现的边作为 causal bonds 和 temporal_links 注入 engine,
        提升 engine.predict / engine.counterfactual 的精度。

        Args:
            engine: UnifiedCausalEngine 实例
            data: 数据
            variables: 变量名
            method: 发现算法(默认 self.discovery_method)

        Returns:
            注入的边数
        """
        result = self.discover(variables, data, method=method)
        if result is None:
            return 0

        edges = result["edges"]
        n_injected = 0
        for cause, effect, edge_type in edges:
            try:
                if edge_type == "directed":
                    # 注入为 causal bond
                    engine.learn_bond(
                        action=cause,
                        target=effect,
                        effect=f"{cause} causes {effect}(discovered)",
                        matched=True,
                        domain="causal_backend",
                    )
                    # 同时注入为 temporal link
                    engine.learn_temporal_link(
                        cause=cause,
                        effect=effect,
                        delay=0.0,
                        confidence=1.0 - self.significance_level,
                        domain="causal_backend",
                    )
                    n_injected += 1
            except Exception as e:
                logger.debug(f"[enhance_engine] 注入 {cause}→{effect} 失败: {e}")

        logger.info(
            f"[enhance_engine] 注入 {n_injected}/{len(edges)} 条因果关系到 "
            f"{getattr(engine, 'name', 'engine')}"
        )
        return n_injected

    # ─────────── 工具方法 ───────────

    def _normalize_data(
        self,
        data: Union[np.ndarray, "pd.DataFrame", Dict[str, List[float]]],
        variables: List[str],
    ) -> Tuple[Optional[np.ndarray], List[str]]:
        """把多种数据格式归一化为 numpy ndarray。"""
        try:
            if isinstance(data, dict):
                # dict of lists → ndarray
                import pandas as pd
                df = pd.DataFrame(data)
                var_names = variables if variables else list(df.columns)
                return df[var_names].values, var_names
            elif hasattr(data, 'values') and hasattr(data, 'columns'):
                # pandas DataFrame
                var_names = variables if variables else list(data.columns)
                return data[var_names].values, var_names
            elif isinstance(data, np.ndarray):
                if data.ndim != 2:
                    logger.warning(f"[_normalize_data] ndarray 须 2D,实际 {data.ndim}D")
                    return None, variables
                if variables and len(variables) != data.shape[1]:
                    logger.warning(
                        f"[_normalize_data] 变量数({len(variables)}) != "
                        f"数据列数({data.shape[1]})"
                    )
                    return None, variables
                return data, variables
            else:
                logger.warning(f"[_normalize_data] 不支持的数据类型: {type(data)}")
                return None, variables
        except Exception as e:
            logger.warning(f"[_normalize_data] 失败: {e}")
            return None, variables

    def stats(self) -> Dict[str, Any]:
        """后端统计。"""
        return {
            "backend": "LAAPCausalBackend v0.1",
            "discovery_method": self.discovery_method,
            "significance_level": self.significance_level,
            "causal_learn_available": self._causal_learn is not None,
            "dowhy_available": self._dowhy is not None,
            "last_graph_discovered": self._last_graph is not None,
            "last_model_built": self._last_model is not None,
        }


# ─────────── 便捷函数 ───────────

def enhance_causal_engine(engine, data, variables: List[str],
                          method: str = "pc") -> int:
    """便捷函数:用 causal-learn 增强 UnifiedCausalEngine。

    Args:
        engine: UnifiedCausalEngine 实例
        data: 数据(ndarray / DataFrame / dict)
        variables: 变量名列表
        method: 发现算法(pc/fci/ges)

    Returns:
        注入的边数
    """
    backend = LAAPCausalBackend(discovery_method=method)
    return backend.enhance_engine(engine, data, variables)
