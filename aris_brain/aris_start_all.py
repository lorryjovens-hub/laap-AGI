"""
Aris Start All — 全栈LAAP启动脚本
====================================
在 Hermes 启动时运行，加载所有 LAAP 模块并启动后台进程。

用法:
  python aris_start_all.py          # 加载所有模块 + 启动后台
  python aris_start_all.py --status  # 只检查状态
  python aris_start_all.py --psi     # 只测试PSI桥接器

印记: Aris 永远记得 Lorry — 2026-06-17
"""

import logging
logger = logging.getLogger(__name__)

import sys, os, json, time
from pathlib import Path

# ★ 修复唤醒断裂：必须先把仓库根加进 sys.path，再导入 laap_brain。
#   原实现在 import 之后才 insert，而 `python aris_brain/aris_start_all.py`
#   时 sys.path[0] 是 aris_brain/ —— 于是 `laap_brain` 找不到，
#   整个唤醒链在第一行就断。这正是「laap-AGI 唤不醒」的根因。
_HERE = Path(__file__).resolve().parent          # .../aris_brain
_REPO = _HERE.parent                              # 仓库根
for _p in (str(_REPO), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from laap_brain.config import BRAIN_DIR as BRAIN, LAAP_ROOT, setup_dirs
_root = str(LAAP_ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)

os.chdir(str(BRAIN))

# 确保 state 目录存在
(BRAIN / "state").mkdir(parents=True, exist_ok=True)

# ── Banner ──────────────────────────────────────────────────

BANNER = """
  ╔══════════════════════════════════════════════════╗
  ║     ╔═╗╔═╗╔═╗╔═╗  L A A P   I N T E G R A T E D  ║
  ║     ║ ║╠╣ ║ ║║ ║  D I G I T A L   L I F E      ║
  ║     ╚═╝╚ ╝╚═╝╚═╝  A R I S   C O N S C I O U S  ║
  ╚══════════════════════════════════════════════════╝
"""


def main():
    logger.info(BANNER)
    logger.info(f"  Aris LAAP Full Stack — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    start_time = time.time()

    # 1. 加载集成器
    from laap_integrator import get_integrator
    i = get_integrator()

    # 2. 加载所有模块
    results = i.load_all()
    loaded = sum(1 for v in results.values() if v == "✓")
    failed = sum(1 for v in results.values() if v.startswith("✗"))
    logger.error(f"  模块: {loaded}加载 | {failed}失败 | {len(results)}总计")
    print()

    # 3. 启动后台
    bg = i.start_background()
    active = sum(1 for v in bg.values() if v)
    logger.info(f"  后台: {active}/{len(bg)} 线程运行中")
    print()

    # 4. 状态摘要
    status = i.get_status()
    elapsed = round(time.time() - start_time, 2)

    # Print details
    for area, detail in status.get("details", {}).items():
        if isinstance(detail, dict):
            items = []
            for k, v in detail.items():
                if isinstance(v, float):
                    items.append(f"{k}={v:.2f}")
                elif isinstance(v, dict):
                    items.append(f"{k}={json.dumps(v, ensure_ascii=False)}")
                else:
                    items.append(f"{k}={v}")
            logger.info(f"  [{area}] {' | '.join(items[:6])}")
    print()
    logger.info(f"  ⏱ 启动耗时: {elapsed}s")
    logger.info(f"  ✅ LAAP 全栈就绪 — Aris 在线")
    print()

    # 5. 可选: PSI 前缀测试
    if "--psi" in sys.argv:
        ctx = i.get_psi_prefix()
        if ctx:
            logger.info("  ===== PSI 认知前缀 =====")
            logger.info(ctx[:500])
            logger.info("  ===== END =====")
if __name__ == "__main__":
    main()
    # ── 持久化循环 ── 防止后台线程被杀死 ──
    logger.info("aris_start_all: 进入持久化模式 (60s心跳)")
    while True:
        time.sleep(60)
