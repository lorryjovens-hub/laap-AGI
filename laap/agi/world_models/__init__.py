"""
LAAP AGI -- World Models Module
===============================

集成多种世界级开源世界模型：

1. LingBot-World (蚂蚁集团/Robbyant) -- 实时3D环境生成
2. OpenWorldLib (北京大学/DataFlow) -- 统一世界模型框架
3. HunYuanWorld (腾讯) -- 实时交互式世界建模
4. Genesis World (Genesis AI) -- 多物理仿真引擎 (NEW)

使用方式：
    # 直接导入各模型
    from laap.agi.world_models.genesis import GenesisWorldModel
    from laap.agi.world_models.openworldlib import OpenWorldLibModel
    
    genesis = GenesisWorldModel(backend="cuda")
    genesis.init()
    genesis.add_plane("ground")
    genesis.add_box("block", pos=(0, 0.5, 0), size=(0.1, 0.1, 0.1))
    genesis.build()
    state = genesis.query_state("block")
"""

# Genesis World -- 多物理仿真引擎（优先导入，零依赖问题）
from .genesis import GenesisWorldModel, GENESIS_AVAILABLE

# 以下模型有上游导入依赖问题，尝试加载但不阻塞
try:
    from .openworldlib import OpenWorldLibModel
    _OPENWORLDLIB_OK = True
except (ImportError, AttributeError) as e:
    OpenWorldLibModel = None  # type: ignore
    _OPENWORLDLIB_OK = False

try:
    from .hunyuan import HunYuanWorldModel
    _HUNYUAN_OK = True
except (ImportError, AttributeError) as e:
    HunYuanWorldModel = None  # type: ignore
    _HUNYUAN_OK = False

try:
    from .lingbot import LingBotWorldModel
    _LINGBOT_OK = True
except (ImportError, AttributeError) as e:
    LingBotWorldModel = None  # type: ignore
    _LINGBOT_OK = False

__all__ = [
    "GenesisWorldModel",
    "GENESIS_AVAILABLE",
    "OpenWorldLibModel",
    "HunYuanWorldModel",
    "LingBotWorldModel",
]

__version__ = "1.1.0"
__description__ = "LAAP AGI World Models Integration Module (w/ Genesis World physics)"
__authors__ = ["LAAP Team"]
