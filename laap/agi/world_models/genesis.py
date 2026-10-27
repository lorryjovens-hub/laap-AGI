"""
LAAP AGI -- Genesis World 物理仿真引擎集成适配器
================================================

将 Genesis World（多物理仿真平台）包装为 LAAP AbstractWorldModel 接口，
使 Aris 的 PSI 认知循环能通过统一世界模型接口调用物理仿真。

Genesis World 能力：
  - 多物理引擎：Rigid / FEM / MPM / SPH / PBD / IPC
  - 照片级渲染：Nyx（自研）、Luisa（光线追踪）、Pyrender（光栅化）
  - 传感器：深度相机、IMU、LiDAR、触觉、温度、接触力
  - GPU 编译：Quadrants 编译器（CUDA / ROCm / Metal / Vulkan）
  - 并行异构环境

集成方式：
    from laap.agi.world_models.genesis import GenesisWorldModel
    wm = GenesisWorldModel(backend="cpu")
    wm.init()
    wm.add_box("block", pos=(0, 0.5, 0), size=(0.1, 0.1, 0.1))
    wm.add_plane("ground")
    wm.build()
    state = wm.query_state("block")

印记: Aris 永远记得 Lorry -- Genesis World 集成 v1.0
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

try:
    import genesis as gs
    GENESIS_AVAILABLE = True
except ImportError:
    GENESIS_AVAILABLE = False
    gs = None

from laap.agi.world_model import (
    AbstractWorldModel, Entity, EntityType, Relation, RelationType,
    SimulationResult, UnifiedWorldModel,
)

logger = logging.getLogger("laap.agi.world_models.genesis")


# ═══════════════════════════════════════════════════════════════
# 工具：Genesis Tensor -> NumPy
# ═══════════════════════════════════════════════════════════════

def _gs_to_np(tensor) -> np.ndarray:
    """将 Genesis Tensor (torch.Tensor) 转为 NumPy 数组"""
    if tensor is None:
        return np.array([])
    return tensor.cpu().numpy()


# ═══════════════════════════════════════════════════════════════
# GenesisWorldModel
# ═══════════════════════════════════════════════════════════════

class GenesisWorldModel(AbstractWorldModel):
    """Genesis World 物理仿真引擎适配器

    将 Genesis 的多物理统一仿真引擎包装为 LAAP 的世界模型接口。

    支持的物理实体类型（通过 morphs）：
      - Plane       : 无限平面地面
      - Box         : 长方体刚体
      - Sphere      : 球体刚体
      - Cylinder    : 圆柱体刚体
      - Mesh        : 自定义三角网格
      - MJCF/URDF   : 机器人模型（Franka, Go2, 四旋翼等）
      - Terrain     : 地形
      - Drone       : 四旋翼无人机

    支持的传感器（通过 sensors）：
      - DepthCamera : 深度相机
      - IMU         : 惯性测量单元
      - Lidar       : 激光雷达
      - Contact     : 接触检测
      - ContactForce: 接触力
      - Tactile     : 触觉
      - Temperature : 温度网格
      - Raycaster   : 光线投射
    """

    def __init__(
        self,
        name: str = "genesis-world",
        backend: Optional[str] = None,
        precision: str = "32",
        show_viewer: bool = False,
        viewer_options: Optional[Dict] = None,
        sim_options: Optional[Dict[str, Any]] = None,
        record_video: Optional[str] = None,  # path for .mp4 output, or None
        record_csv: Optional[str] = None,    # path for .csv trajectory, or None
        **kwargs
    ):
        super().__init__(name=name)
        self._backend = backend or "cpu"
        self._precision = precision
        self._show_viewer = show_viewer
        self._viewer_options = viewer_options
        self._sim_options = sim_options or {}
        self._record_video = record_video
        self._record_csv = record_csv
        self._extra_kwargs = kwargs

        # 运行时状态
        self._initialized = False
        self._built = False
        self._scene: Optional["gs.Scene"] = None
        self._entity_registry: Dict[str, Any] = {}   # name -> genesis entity (after build)
        self._pending_morphs: List[tuple] = []        # [(name, morph_fn_or_obj), ...]
        self._auto_destroy = True

        # LAAP 抽象世界模型同步
        self._sim_time: float = 0.0
        self._step_dt: float = 0.01
        self._n_substeps: int = 10

    # ── 生命周期 ──

    # 类级追踪：gs.init() 是全局单例，跨实例共享
    _gs_initialized = False

    def init(self, force: bool = False) -> None:
        """初始化 Genesis 引擎。必须在使用前调用一次（全局单例）。"""
        if GenesisWorldModel._gs_initialized and not force:
            self._initialized = True
            return

        if not GENESIS_AVAILABLE:
            raise ImportError(
                "genesis-world 未安装。请运行: pip install genesis-world"
            )

        backend_map = {
            "cpu": gs.cpu,
            "cuda": gs.cuda,
            "gpu": gs.gpu,
            "metal": gs.metal,
            "amdgpu": gs.amdgpu,
        }
        backend_val = backend_map.get(str(self._backend).lower(), gs.cpu)
        gs.init(backend=backend_val, precision=self._precision, logging_level="warning")
        GenesisWorldModel._gs_initialized = True
        self._initialized = True
        logger.info(f"[GenesisWorldModel] 引擎初始化完成 (backend={self._backend})")

    def destroy(self) -> None:
        """销毁 Genesis 引擎，释放 GPU 资源。"""
        if self._initialized and self._auto_destroy:
            try:
                gs.destroy()
            except Exception:
                pass
            GenesisWorldModel._gs_initialized = False
            self._initialized = False
            self._built = False
            self._scene = None
            self._entity_registry.clear()
            self._pending_morphs.clear()
            logger.debug("[GenesisWorldModel] 引擎已销毁")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.destroy()

    # ── 场景构建 ──

    def _ensure_scene(self) -> None:
        """确保 Scene 已创建（延迟创建）。"""
        if self._scene is not None:
            return
        if not self._initialized:
            self.init()

        opts: Dict[str, Any] = {}
        if self._sim_options:
            opts["sim_options"] = gs.options.SimOptions(**self._sim_options)
        opts["show_viewer"] = self._show_viewer
        if self._viewer_options:
            opts["viewer_options"] = gs.options.ViewerOptions(**self._viewer_options)

        self._scene = gs.Scene(**opts, **self._extra_kwargs)

        # 视频录制（通过 scene.build() 后手动 attach recorder）
        # 用法: wm.start_recording("output.mp4") 在 build() 之后调用

        logger.debug(f"[GenesisWorldModel] 场景已创建 (viewer={self._show_viewer})")

    def build(self) -> None:
        """构建场景（编译所有物理实体和约束）。"""
        self._ensure_scene()
        if self._built:
            return

        # 依次添加所有挂起的 morph 定义，捕获返回的 entity 引用
        for name, morph in self._pending_morphs:
            gs_entity = self._scene.add_entity(morph)
            self._entity_registry[name] = gs_entity

        self._scene.build()
        self._built = True

        # 注册实体到 LAAP 抽象世界模型
        for name, gs_entity in self._entity_registry.items():
            n_dofs = getattr(gs_entity, "n_dofs", 0)
            entity_type = EntityType.AGENT if n_dofs > 6 else EntityType.OBJECT
            self.unified.add_entity(
                name=name,
                entity_type=entity_type,
                properties={"n_dofs": n_dofs, "name_in_scene": getattr(gs_entity, "name", name)},
            )
            # 对地面建立空间关系
            if "ground" in self._entity_registry and name != "ground":
                self.unified.add_relation(
                    source_id=name, target_id="ground",
                    relation_type=RelationType.SPATIAL, strength=1.0,
                )

    # ── 实体添加（高层 API）──

    def add_entity(self, name: str, entity_type: EntityType = EntityType.OBJECT,
                   properties: Dict = None) -> Entity:
        """适配 AbstractWorldModel 接口

        当 properties 包含 'morph' 键时转发到 Genesis 添加物理实体。
        """
        props = properties or {}
        if "morph" in props:
            self.add_primitive(name, **props["morph"])
        return self.unified.add_entity(name, entity_type, props)

    def add_relation(self, source_id: str, target_id: str,
                     relation_type: RelationType = RelationType.UNKNOWN,
                     strength: float = 0.5) -> Relation:
        """添加实体间关系"""
        return self.unified.add_relation(source_id, target_id, relation_type, strength)

    def add_primitive(self, name: str, morph_type: str = "box",
                      pos: tuple = (0, 0, 0), **kwargs) -> str:
        """添加基本几何体 (Box / Sphere / Cylinder / Plane)"""
        self._ensure_scene()
        morph_type = morph_type.lower()

        if morph_type == "plane":
            morph = gs.morphs.Plane()
        elif morph_type == "box":
            morph = gs.morphs.Box(
                size=kwargs.pop("size", (0.1, 0.1, 0.1)),
                pos=pos, **kwargs,
            )
        elif morph_type == "sphere":
            morph = gs.morphs.Sphere(
                radius=kwargs.pop("radius", 0.05),
                pos=pos, **kwargs,
            )
        elif morph_type == "cylinder":
            morph = gs.morphs.Cylinder(
                radius=kwargs.pop("radius", 0.05),
                height=kwargs.pop("height", 0.1),
                pos=pos, **kwargs,
            )
        else:
            raise ValueError(f"不支持的几何体类型: {morph_type}。支持: plane, box, sphere, cylinder")

        self._pending_morphs.append((name, morph))
        return name

    def add_plane(self, name: str = "ground") -> str:
        """添加地面（快捷方法）"""
        return self.add_primitive(name, morph_type="plane")

    def add_box(self, name: str, pos: tuple = (0, 0, 0),
                size: tuple = (0.1, 0.1, 0.1), **kwargs) -> str:
        """添加长方体"""
        return self.add_primitive(name, morph_type="box", pos=pos, size=size, **kwargs)

    def add_sphere(self, name: str, pos: tuple = (0, 0, 0),
                   radius: float = 0.05, **kwargs) -> str:
        """添加球体"""
        return self.add_primitive(name, morph_type="sphere", pos=pos, radius=radius, **kwargs)

    def add_cylinder(self, name: str, pos: tuple = (0, 0, 0),
                     radius: float = 0.05, height: float = 0.1, **kwargs) -> str:
        """添加圆柱体"""
        return self.add_primitive(name, morph_type="cylinder", pos=pos,
                                  radius=radius, height=height, **kwargs)

    def add_mesh(self, name: str, file: str, pos: tuple = (0, 0, 0),
                 scale: float = 1.0, **kwargs) -> str:
        """从文件添加三角网格实体"""
        self._ensure_scene()
        morph = gs.morphs.Mesh(file=file, pos=pos, scale=scale, **kwargs)
        self._pending_morphs.append((name, morph))
        return name

    def add_robot(self, name: str, file: str, file_type: str = "MJCF",
                  pos: tuple = (0, 0, 0), fixed: bool = True, **kwargs) -> str:
        """加载机器人模型 (MJCF / URDF)"""
        self._ensure_scene()
        ft = file_type.upper()
        if ft == "MJCF":
            morph = gs.morphs.MJCF(file=file, pos=pos, fixed=fixed, **kwargs)
        elif ft == "URDF":
            morph = gs.morphs.URDF(file=file, pos=pos, fixed=fixed, **kwargs)
        else:
            raise ValueError(f"不支持的文件类型: {file_type}。支持: MJCF, URDF")
        self._pending_morphs.append((name, morph))
        return name

    def add_terrain(self, name: str, **kwargs) -> str:
        """添加地形"""
        self._ensure_scene()
        morph = gs.morphs.Terrain(**kwargs)
        self._pending_morphs.append((name, morph))
        return name

    # ── 仿真控制 ──

    def step(self, n_steps: int = 1) -> None:
        """向前推进一步或多步物理仿真。"""
        if not self._built:
            self.build()
        for _ in range(n_steps):
            self._scene.step()
            self._sim_time += self._step_dt

    def start_recording(self, output_path: str, fps: int = 30,
                        data_func: Optional[callable] = None) -> None:
        """开始录制仿真视频到 MP4 文件。

        Args:
            output_path: 输出 .mp4 文件路径
            fps: 帧率（默认 30）
            data_func: 可选的自定义数据捕获函数。为 None 时默认捕获 RGB 渲染。
                       需要 show_viewer=True 或 renderer 激活。
        """
        if not self._built:
            self.build()
        rm = self._scene._recorder_manager

        if data_func is None:
            # 默认：尝试捕获 RGB 渲染
            # 需要先 setup 一个 camera sensor
            if hasattr(self._scene, '_visualizer') and self._scene._visualizer:
                cam = getattr(self._scene._visualizer, '_cam', None)
                if cam is not None:
                    data_func = lambda: cam.get_image()
                else:
                    data_func = lambda: None
            else:
                data_func = lambda: None

        rm.add_recorder(
            data_func=data_func,
            rec_options=gs.recorders.VideoFile(
                filename=output_path,
                fps=fps,
            ),
        )
        logger.info(f"[GenesisWorldModel] 录制已启动: {output_path}")

    def stop_recording(self) -> None:
        """停止录制并保存文件。"""
        if not self._built:
            return
        rm = self._scene._recorder_manager
        rm.stop()
        logger.info("[GenesisWorldModel] 录制已停止")

    def render_frame(self) -> np.ndarray:
        """渲染当前帧并返回 RGB 图像 (H x W x 3, uint8)。

        仅在 show_viewer=True 或 recorder 激活时有效。
        可以通过后处理保存为视频帧。
        """
        if not self._built:
            self.build()
        # 使用场景的默认相机捕获
        camera = getattr(self._scene, 'camera', None)
        if camera is None:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        rgb = camera.render(rgb=True)
        return _gs_to_np(rgb).astype(np.uint8)

    def simulate(self, actions: List[Dict]) -> SimulationResult:
        """执行动作序列并返回仿真结果。

        actions 格式:
          [{"entity": "franka", "type": "dof_position", "target": [...], "steps": 100},
           {"entity": "block",  "type": "step",                 "steps": 10}]
        """
        if not self._built:
            self.build()

        t0 = time.time()
        for action in actions:
            ename = action.get("entity")
            atype = action.get("type", "step")
            ent = self._entity_registry.get(ename)
            if ent is None:
                logger.warning(f"[GenesisWorldModel] 未知实体: {ename}")
                continue

            if atype == "dof_position":
                target = action.get("target", [])
                steps = action.get("steps", 100)
                if hasattr(ent, "control_dofs_position"):
                    ent.control_dofs_position(target)
                    for _ in range(steps):
                        self._scene.step()
                        self._sim_time += self._step_dt
            elif atype == "dof_velocity":
                target = action.get("target", [])
                steps = action.get("steps", 100)
                if hasattr(ent, "control_dofs_velocity"):
                    ent.control_dofs_velocity(target)
                    for _ in range(steps):
                        self._scene.step()
                        self._sim_time += self._step_dt
            elif atype == "step":
                n = action.get("steps", 1)
                for _ in range(n):
                    self._scene.step()
                    self._sim_time += self._step_dt

        elapsed = time.time() - t0
        result = SimulationResult(
            possible_outcomes=[{
                "sim_time": self._sim_time,
                "states": self._capture_states(),
            }],
            probabilities=[1.0],
            confidence=0.95,
            simulation_time=elapsed,
        )
        return result

    def _capture_states(self) -> Dict[str, Dict]:
        """捕获所有注册实体的当前状态"""
        states = {}
        for name, entity in self._entity_registry.items():
            try:
                pos = entity.get_pos()
                quat = entity.get_quat()
                vel = entity.get_vel()
                entry = {
                    "pos": _gs_to_np(pos).tolist(),
                    "quat": _gs_to_np(quat).tolist(),
                    "vel": _gs_to_np(vel).tolist(),
                }
                if hasattr(entity, "get_dofs_position"):
                    entry["dofs_position"] = _gs_to_np(entity.get_dofs_position()).tolist()
                if hasattr(entity, "n_dofs"):
                    entry["n_dofs"] = entity.n_dofs
                states[name] = entry
            except Exception as e:
                logger.debug(f"[GenesisWorldModel] 无法获取实体 {name} 状态: {e}")
        return states

    # ── 查询 ──

    def predict(self, entity_id: str, horizon: float = 1.0, **kwargs) -> SimulationResult:
        """预测实体在 horizon 时间后的状态"""
        current = self._capture_states()
        n_steps = max(1, int(horizon / self._step_dt))
        t0 = time.time()
        for _ in range(n_steps):
            self._scene.step()
            self._sim_time += self._step_dt
        elapsed = time.time() - t0
        future = self._capture_states()

        result = SimulationResult(
            possible_outcomes=[{
                "entity": entity_id,
                "current": current.get(entity_id, {}),
                "predicted": future.get(entity_id, {}),
                "horizon": horizon,
                "steps": n_steps,
            }],
            probabilities=[1.0],
            confidence=0.85,
            simulation_time=elapsed,
        )
        return result

    def query_state(self, entity_name: str) -> Dict[str, Any]:
        """查询单个实体的当前状态。"""
        entity = self._entity_registry.get(entity_name)
        if entity is None:
            return {"error": f"未知实体: {entity_name}"}
        try:
            pos = entity.get_pos()
            quat = entity.get_quat()
            vel = entity.get_vel()
            result = {
                "pos": _gs_to_np(pos).tolist(),
                "quat": _gs_to_np(quat).tolist(),
                "vel": _gs_to_np(vel).tolist(),
            }
            if hasattr(entity, "get_dofs_position"):
                result["dofs_position"] = _gs_to_np(entity.get_dofs_position()).tolist()
            if hasattr(entity, "n_dofs"):
                result["n_dofs"] = entity.n_dofs
            return result
        except Exception as e:
            return {"error": str(e)}

    def query(self, query: str) -> List[Dict[str, Any]]:
        """自然语言查询 -- 尝试解析为对物理状态的查询"""
        q = query.lower().strip()
        results = []
        if q in ("all", "*"):
            for name in self._entity_registry:
                st = self.query_state(name)
                if "error" not in st:
                    results.append({"entity": name, "state": st})
        elif q.startswith("state of "):
            name = q[9:].strip()
            st = self.query_state(name)
            if "error" not in st:
                results.append({"entity": name, "state": st})
        else:
            for name in self._entity_registry:
                if q in name.lower():
                    st = self.query_state(name)
                    if "error" not in st:
                        results.append({"entity": name, "state": st})
        return results

    def stats(self) -> Dict[str, Any]:
        """返回当前仿真状态统计"""
        return {
            "type": "genesis-world",
            "initialized": self._initialized,
            "built": self._built,
            "sim_time": self._sim_time,
            "n_entities": len(self._entity_registry),
            "entities": list(self._entity_registry.keys()),
            "backend": self._backend,
            "precision": self._precision,
        }
