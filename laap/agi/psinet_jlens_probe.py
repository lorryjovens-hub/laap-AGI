"""J-lens 拟合与探测接口（LAAP Ψ-Net / Psi-Net 内部模型）.

核心公式::

    lens_l(h) = unembed(J_l @ h)
    J_l       = E[ ∂h_final / ∂h_l ]

本模块提供:
    * ``JlensConfig``      — J-lens 配置数据类
    * ``PsiNetModelWrapper`` — 模型封装协议
    * ``JlensFitter``      — 从语料拟合 J_l 矩阵
    * ``PsiNetJlensProbe`` — 读取/干预 J-space 概念，并可选发布到 CognitiveBus
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Callable,
    Iterable,
    Iterator,
    Protocol,
    Sequence,
    runtime_checkable,
)

import numpy as np

logger = logging.getLogger("laap.agi.psinet_jlens_probe")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


@dataclass
class JlensConfig:
    """J-lens 拟合与探测配置."""

    source_layers: list[dict[str, Any]] = field(default_factory=list)
    sequence_length: int = 32
    topk: int = 5
    activation_threshold: float = 0.15
    attribution_method: str = "jacobian"
    n_samples_per_sequence: int = 10
    epsilon: float = 1e-3
    cache_dir: Path = field(default_factory=lambda: Path("./cache"))
    random_seed: int | None = 42

    def __post_init__(self) -> None:
        """归一化路径字段."""
        if isinstance(self.cache_dir, str):
            object.__setattr__(self, "cache_dir", Path(self.cache_dir))

    @classmethod
    def from_experiment_config(cls, config: dict[str, Any]) -> "JlensConfig":
        """从 ``config.yaml`` 的 ``jlens`` 节构建配置."""
        jlens = config.get("jlens", {})
        paths = config.get("paths", {})
        stats = config.get("statistics", {})
        root = Path(__file__).resolve().parents[2] / "experiments" / "jspace_laap"
        cache = root / paths.get("cache", "./cache").lstrip("./")
        return cls(
            source_layers=jlens.get("source_layers", []),
            sequence_length=int(jlens.get("sequence_length", 32)),
            topk=int(jlens.get("topk", 5)),
            activation_threshold=float(jlens.get("activation_threshold", 0.15)),
            attribution_method=jlens.get("attribution_method", "jacobian"),
            n_samples_per_sequence=int(jlens.get("n_samples_per_sequence", 10)),
            cache_dir=cache,
            random_seed=stats.get("random_seed"),
        )


# ---------------------------------------------------------------------------
# 模型协议
# ---------------------------------------------------------------------------


@runtime_checkable
class PsiNetModelWrapper(Protocol):
    """Psi-Net / LAAP 内部模型封装协议.

    实现者必须暴露层数、隐藏状态读取、最终状态读取、反嵌入以及
    从任意层隐藏状态继续前向传播的能力（供有限差分使用）。
    """

    n_layers: int

    def get_hidden_state(self, inputs: Any, layer: int) -> np.ndarray | Any:
        """返回第 ``layer`` 层的隐藏状态 ``h_l``."""
        ...

    def get_final_state(self, inputs: Any) -> np.ndarray | Any:
        """返回最终隐藏状态 ``h_final``."""
        ...

    def get_final_state_from_hidden(
        self,
        hidden_state: np.ndarray | Any,
        layer: int,
    ) -> np.ndarray | Any:
        """从第 ``layer`` 层的 ``hidden_state`` 继续前向到最终层."""
        ...

    def unembed(self, final_state: np.ndarray | Any) -> np.ndarray | Any:
        """将最终隐藏状态映射为输出空间（logits / token 分布）."""
        ...

    def forward_with_intervention(
        self,
        inputs: Any,
        interventions: dict[int, np.ndarray] | Sequence[tuple[int, np.ndarray]],
    ) -> np.ndarray | Any:
        """对指定层施加 J-space 干预后前向传播.

        ``interventions`` 可以是 ``{layer: vector}`` 映射，或
        ``[(layer, vector), ...]`` 序列。``vector`` 为 J-space 向量。
        """
        ...


# ---------------------------------------------------------------------------
# J-lens 拟合器
# ---------------------------------------------------------------------------


class JlensFitter:
    """拟合 J_l = E[∂h_final / ∂h_l] 矩阵."""

    def __init__(
        self,
        model: PsiNetModelWrapper,
        config: JlensConfig | None = None,
    ):
        self.model = model
        self.config = config or JlensConfig()
        self.J: list[np.ndarray] | None = None

        # 源层定义与索引映射
        self._source_layers: list[dict[str, Any]] = self._resolve_source_layers()
        self._layer_to_jidx: dict[int, int] = {
            sl["idx"]: i for i, sl in enumerate(self._source_layers)
        }

        # 线程安全锁
        self._fit_lock = threading.Lock()
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------

    def _cache_identifier(self, suffix: str = "") -> str:
        """生成缓存文件标识符，包含模型层数与源层索引."""
        layer_ids = "_".join(str(sl["idx"]) for sl in self._source_layers)
        return (
            f"jlens_L{self.model.n_layers}_layers{layer_ids}_"
            f"eps{self.config.epsilon}_{self.config.attribution_method}{suffix}"
        )

    def _cache_path(self, suffix: str = "") -> Path:
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        return self.config.cache_dir / f"{self._cache_identifier(suffix)}.npz"

    def _metadata_path(self, suffix: str = "") -> Path:
        return self._cache_path(suffix).with_suffix(".json")

    def _save_cache(self, suffix: str = "") -> None:
        with self._cache_lock:
            if self.J is None:
                return
            path = self._cache_path(suffix)
            np.savez(path, *[j.astype(np.float32) for j in self.J])
            meta = {
                "n_layers": self.model.n_layers,
                "source_layers": self._source_layers,
                "shapes": [j.shape for j in self.J],
                "epsilon": self.config.epsilon,
                "method": self.config.attribution_method,
            }
            self._metadata_path(suffix).write_text(
                json.dumps(meta, indent=2, default=str), encoding="utf-8"
            )
            logger.info(f"J-lens 缓存已保存: {path}")

    def _load_cache(self, suffix: str = "") -> list[np.ndarray] | None:
        with self._cache_lock:
            path = self._cache_path(suffix)
            meta_path = self._metadata_path(suffix)
            if not path.is_file() or not meta_path.is_file():
                return None
            try:
                data = np.load(path)
                J = [data[f"arr_{i}"] for i in range(len(data.files))]
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("n_layers") != self.model.n_layers:
                    logger.warning("J-lens 缓存层数不匹配，重新拟合")
                    return None
                cached_layers = meta.get("source_layers", [])
                if [sl["idx"] for sl in cached_layers] != [
                    sl["idx"] for sl in self._source_layers
                ]:
                    logger.warning("J-lens 缓存源层索引不匹配，重新拟合")
                    return None
                logger.info(f"J-lens 缓存已加载: {path}")
                return J
            except Exception as exc:
                logger.warning(f"加载 J-lens 缓存失败: {exc}")
                return None

    # ------------------------------------------------------------------
    # 拟合入口
    # ------------------------------------------------------------------

    def fit(
        self,
        corpus_loader: Iterable[Any] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        use_cache: bool = True,
        cache_suffix: str = "",
    ) -> list[np.ndarray]:
        """拟合所有源层的 J_l 矩阵.

        Args:
            corpus_loader: 语料迭代器，每次产出可传给 ``model.get_hidden_state`` 的输入。
                若为 ``None``，使用配置中的默认语料生成随机样本。
            progress_callback: 进度回调 ``(current, total, message)``。
            use_cache: 是否尝试读取/写入缓存。
            cache_suffix: 缓存文件后缀，用于区分模型或语料版本。

        Returns:
            每个源层对应的 J_l 矩阵列表（顺序与 ``source_layers`` 一致）。

        Raises:
            RuntimeError: 当拟合过程中发生不可恢复错误时。
        """
        with self._fit_lock:
            if use_cache:
                cached = self._load_cache(cache_suffix)
                if cached is not None:
                    self.J = cached
                    return self.J

            if self.config.random_seed is not None:
                np.random.seed(self.config.random_seed)

            corpus_loader = corpus_loader or self._default_corpus_loader()

            try:
                if self._is_torch_module(self.model):
                    logger.info("使用 torch 自动微分拟合 J-lens")
                    self.J = self._fit_with_torch(corpus_loader, progress_callback)
                else:
                    logger.info("使用有限差分拟合 J-lens（fallback）")
                    self.J = self._fit_with_finite_difference(
                        corpus_loader, progress_callback
                    )
            except Exception as exc:
                raise RuntimeError(f"J-lens 拟合失败: {exc}") from exc

            if not self.J:
                raise RuntimeError("J-lens 拟合结果为空")

            expected = [sl["idx"] for sl in self._source_layers]
            logger.info(
                f"J-lens 拟合完成，源层={expected}, "
                f"J_l 形状={[j.shape for j in self.J]}"
            )

            if use_cache:
                self._save_cache(cache_suffix)
            return self.J

    # ------------------------------------------------------------------
    # 内部：语料加载器
    # ------------------------------------------------------------------

    def _default_corpus_loader(self) -> Iterator[np.ndarray]:
        """默认生成随机 token id 序列作为语料."""
        vocab_size = getattr(self.model, "vocab_size", 1000)
        seq_len = self.config.sequence_length
        n = self.config.n_samples_per_sequence
        for _ in range(n):
            yield np.random.randint(0, vocab_size, size=(1, seq_len), dtype=np.int64)

    # ------------------------------------------------------------------
    # 内部：源层解析
    # ------------------------------------------------------------------

    def _resolve_source_layers(self) -> list[dict[str, Any]]:
        """归一化源层配置."""
        if self.config.source_layers:
            return [
                {"name": sl.get("name", f"layer_{sl['idx']}"), "idx": int(sl["idx"])}
                for sl in self.config.source_layers
            ]
        return [
            {"name": f"layer_{l}", "idx": l} for l in range(self.model.n_layers)
        ]

    # ------------------------------------------------------------------
    # 内部：模型类型探测
    # ------------------------------------------------------------------

    @staticmethod
    def _is_torch_module(model: Any) -> bool:
        try:
            import torch.nn as nn

            return isinstance(model, nn.Module)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 内部：torch 自动微分
    # ------------------------------------------------------------------

    def _fit_with_torch(
        self,
        corpus_loader: Iterable[Any],
        progress_callback: Callable[[int, int, str], None] | None,
    ) -> list[np.ndarray]:
        import torch

        n_layers = len(self._source_layers)

        corpus = list(corpus_loader)
        if not corpus:
            raise ValueError("corpus_loader 未产出任何样本")

        sample = corpus[0]
        if isinstance(sample, (list, tuple)):
            sample = sample[0]
        h0 = self.model.get_hidden_state(sample, self._source_layers[0]["idx"])
        d_model = int(np.asarray(h0).shape[-1])

        accum: list[list[np.ndarray]] = [[] for _ in range(n_layers)]

        for step, batch in enumerate(corpus):
            if isinstance(batch, (list, tuple)):
                inputs = batch[0]
            else:
                inputs = batch

            for li, layer_def in enumerate(self._source_layers):
                layer_idx = layer_def["idx"]
                h_l = self.model.get_hidden_state(inputs, layer_idx)
                if isinstance(h_l, np.ndarray):
                    h_l_t = torch.from_numpy(h_l).requires_grad_(True)
                else:
                    h_l_t = h_l.detach().clone().requires_grad_(True)

                mean_h_l = h_l_t.mean(dim=tuple(range(h_l_t.ndim - 1)))

                def _fwd(z: Any) -> Any:
                    # 将 d 维均值向量广播回原始形状后继续前向
                    shape = [1] * (h_l_t.ndim - 1) + [d_model]
                    h_broadcast = z.view(*shape).expand_as(h_l_t)
                    h_final = self.model.get_final_state_from_hidden(
                        h_broadcast, layer_idx
                    )
                    if isinstance(h_final, np.ndarray):
                        h_final = torch.from_numpy(h_final)
                    return h_final.mean(dim=tuple(range(h_final.ndim - 1)))

                jac = torch.autograd.functional.jacobian(_fwd, mean_h_l)
                accum[li].append(jac.detach().cpu().numpy())

                if progress_callback is not None:
                    progress_callback(
                        step + 1,
                        len(corpus),
                        f"torch layer {layer_def['name']}",
                    )

        J = [np.mean(np.stack(mats, axis=0), axis=0) for mats in accum]
        return J

    # ------------------------------------------------------------------
    # 内部：有限差分
    # ------------------------------------------------------------------

    def _fit_with_finite_difference(
        self,
        corpus_loader: Iterable[Any],
        progress_callback: Callable[[int, int, str], None] | None,
    ) -> list[np.ndarray]:
        sample = next(iter(corpus_loader))
        if isinstance(sample, (list, tuple)):
            sample = sample[0]
        h0 = self.model.get_hidden_state(sample, self._source_layers[0]["idx"])
        d_model = int(np.asarray(h0).shape[-1])

        n_layers = len(self._source_layers)
        accum: list[np.ndarray] = [
            np.zeros((d_model, d_model), dtype=np.float64)
            for _ in range(n_layers)
        ]
        count = 0

        for step, batch in enumerate(corpus_loader):
            if isinstance(batch, (list, tuple)):
                inputs = batch[0]
            else:
                inputs = batch

            for li, layer_def in enumerate(self._source_layers):
                layer_idx = layer_def["idx"]
                h_l = np.asarray(self.model.get_hidden_state(inputs, layer_idx))
                h_final = np.asarray(self.model.get_final_state(inputs))

                if h_l.shape[-1] != d_model or h_final.shape[-1] != d_model:
                    raise ValueError(
                        f"层 {layer_idx} 隐藏状态维度不一致: "
                        f"h_l={h_l.shape}, h_final={h_final.shape}"
                    )

                # 在 h_l 的第 j 个维度施加微小扰动，观察 h_final 的变化
                for j in range(d_model):
                    h_pert = h_l.copy()
                    h_pert[..., j] += self.config.epsilon
                    h_final_pert = np.asarray(
                        self.model.get_final_state_from_hidden(h_pert, layer_idx)
                    )
                    delta = (h_final_pert - h_final) / self.config.epsilon
                    # 对 batch 和 seq 维度取平均，得到 ∂h_final/∂h_l[:,j]
                    mean_deriv = delta.reshape(-1, d_model).mean(axis=0)
                    accum[li][:, j] += mean_deriv

                if progress_callback is not None:
                    progress_callback(
                        step + 1,
                        n_layers,
                        f"fd layer {layer_def['name']}",
                    )

            count += 1

        if count == 0:
            raise ValueError("corpus_loader 未产出任何样本")

        J = [m / count for m in accum]
        return J

    # ------------------------------------------------------------------
    # 公共辅助
    # ------------------------------------------------------------------

    def get_J_for_layer(self, layer_idx: int) -> np.ndarray:
        """获取指定源层对应的 J_l 矩阵."""
        if self.J is None:
            raise ValueError("JlensFitter 尚未拟合 J_l，请先调用 fit()")
        jidx = self._layer_to_jidx.get(layer_idx)
        if jidx is None:
            raise ValueError(
                f"层 {layer_idx} 不在源层列表 "
                f"{list(self._layer_to_jidx.keys())} 中"
            )
        return self.J[jidx]


# ---------------------------------------------------------------------------
# J-lens 探测与干预
# ---------------------------------------------------------------------------


class PsiNetJlensProbe:
    """基于 J-lens 的概念读取与干预探针."""

    def __init__(
        self,
        model: PsiNetModelWrapper,
        fitter: JlensFitter,
        config: JlensConfig | None = None,
    ):
        self.model = model
        self.fitter = fitter
        self.config = config or fitter.config
        self.J = fitter.J
        if self.J is None:
            raise ValueError("JlensFitter 尚未拟合 J_l，请先调用 fit()")

        self._layer_to_jidx = fitter._layer_to_jidx
        self._read_lock = threading.Lock()
        self._intervene_lock = threading.Lock()

    def read(self, inputs: Any, layer: int) -> dict[str, Any]:
        """读取单层的 J-space 活跃概念.

        Returns:
            包含 ``layer``、``layer_name``、``lens_logits``、``topk_concepts``、
            ``activations`` 的字典。
        """
        with self._read_lock:
            layer_def = self._resolve_layer(layer)
            layer_idx = layer_def["idx"]
            J_l = self.fitter.get_J_for_layer(layer_idx)

            h_l = np.asarray(self.model.get_hidden_state(inputs, layer_idx))

            # lens_l(h) = unembed(J_l @ h)
            # 对 batch*seq 所有 token 位置分别计算后取平均
            flat_h = h_l.reshape(-1, h_l.shape[-1])
            j_space = flat_h @ J_l.T
            lens_logits = np.asarray(
                self.model.unembed(j_space.reshape(h_l.shape))
            )
            mean_logits = lens_logits.reshape(-1, lens_logits.shape[-1]).mean(axis=0)

            # 过滤低于阈值的激活
            active_mask = mean_logits >= self.config.activation_threshold
            active_idx = np.where(active_mask)[0]
            if active_idx.size == 0:
                active_idx = np.arange(mean_logits.size)

            topk_idx = active_idx[np.argsort(-mean_logits[active_idx])]
            topk_idx = topk_idx[: self.config.topk]

            topk = [
                {"token_id": int(tok), "logit": float(mean_logits[tok])}
                for tok in topk_idx
            ]

            return {
                "layer": layer_idx,
                "layer_name": layer_def.get("name", f"layer_{layer_idx}"),
                "lens_logits_shape": list(lens_logits.shape),
                "topk_concepts": topk,
                "activations": {
                    "mean": float(mean_logits.mean()),
                    "max": float(mean_logits.max()),
                    "min": float(mean_logits.min()),
                },
            }

    def read_all_layers(self, inputs: Any) -> dict[str, Any]:
        """多层联合读取 J-space 内容."""
        readings = []
        for layer_def in self.config.source_layers:
            readings.append(self.read(inputs, layer_def["idx"]))
        return {
            "n_layers": len(readings),
            "readings": readings,
        }

    def intervene(
        self,
        inputs: Any,
        interventions: dict[int, np.ndarray] | Sequence[tuple[int, np.ndarray]],
    ) -> dict[str, Any]:
        """对指定层应用 J-space 干预并返回前后输出.

        Returns:
            包含 ``baseline_logits``、``intervened_logits``、``delta``、
            ``interventions`` 的字典。
        """
        with self._intervene_lock:
            baseline = np.asarray(self.model.unembed(self.model.get_final_state(inputs)))
            intervened = np.asarray(
                self.model.forward_with_intervention(inputs, interventions)
            )
            delta = intervened - baseline

            return {
                "baseline_logits_shape": list(baseline.shape),
                "intervened_logits_shape": list(intervened.shape),
                "delta_shape": list(delta.shape),
                "baseline_mean": float(baseline.mean()),
                "intervened_mean": float(intervened.mean()),
                "delta_mean": float(delta.mean()),
                "delta_std": float(delta.std()),
            }

    def publish_to_bus(
        self,
        reading: dict[str, Any],
        bus: Any,
        rate_buffer: Any | None = None,
    ) -> None:
        """将 J-lens 读数发布到 CognitiveBus / RateBuffer（可选）."""
        try:
            from laap.agi.cognitive_bus import CognitiveEventType

            event_type = CognitiveEventType.CONSCIOUS_FRAME
        except Exception:
            event_type = "J_LENS_READING"

        payload = {
            "source": "jlens_probe",
            "event_type": str(event_type),
            "reading": reading,
        }

        if rate_buffer is not None and hasattr(rate_buffer, "push"):
            rate_buffer.push(payload)
            return

        if bus is not None and hasattr(bus, "publish"):
            bus.publish(event_type, "jlens_probe", payload)
            return

        logger.debug(
            f"未提供有效的 bus 或 rate_buffer，读数未发布: {reading.get('layer_name')}"
        )

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _resolve_layer(self, layer: int) -> dict[str, Any]:
        matches = [sl for sl in self.config.source_layers if sl["idx"] == layer]
        if matches:
            return matches[0]
        return {"name": f"layer_{layer}", "idx": layer}


# ---------------------------------------------------------------------------
# 便捷：从配置直接构建探测器的工厂函数
# ---------------------------------------------------------------------------


def build_jlens_probe(
    model: PsiNetModelWrapper,
    config: dict[str, Any] | JlensConfig | None = None,
    corpus_loader: Iterable[Any] | None = None,
    use_cache: bool = True,
) -> PsiNetJlensProbe:
    """一站式构建并拟合 J-lens 探针."""
    if isinstance(config, JlensConfig):
        jlens_config = config
    else:
        jlens_config = JlensConfig.from_experiment_config(config or {})

    fitter = JlensFitter(model, jlens_config)
    fitter.fit(corpus_loader=corpus_loader, use_cache=use_cache)
    return PsiNetJlensProbe(model, fitter, jlens_config)
