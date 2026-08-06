"""
Aris Governor Hourly Audit — 慢时间尺度审计守护脚本
===================================================

每小时运行一次，检查 PSI 需求轨迹是否有异常漂移。
如果检测到 LLM 操控或宪法违反，自动进入保护模式。

集成方式:
  cronjob(script='governor_hourly_audit.py', schedule='1h')
"""

import json
import os
import sys
import time

GOVERNOR_DIR = os.path.dirname(os.path.abspath(__file__))
BRIDGE_DIR = os.path.join(GOVERNOR_DIR, "..")
sys.path.insert(0, GOVERNOR_DIR)

from aris_brain.psi_jspace_bridge.governor.governor_core import PSIGovernor

# 加载 Governor
gov = PSIGovernor()

# 运行审计
report = gov.run_hourly_audit(force=True)

# 结果
print(f"[Governor Audit] {report.get('timestamp', '?')}")
print(f"  Mode: {gov.mode}")
print(f"  Interventions: {gov._intervention_count}")
print(f"  Alerts: {len(report.get('alerts', []))}")

if report.get("alerts"):
    print("  ⚠ ALERTS:")
    for a in report["alerts"]:
        print(f"    - {a}")

if not report.get("constitutional_compliance", True):
    print("  ❗ CONSTITUTION VIOLATION DETECTED")
    print("  → Governor entering freeze/safety mode")

# 如果进入冻结模式，更新 psi_state.json 以同步
state_path = os.path.join(BRIDGE_DIR, "psi_state.json")
if os.path.exists(state_path):
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        state["governor"] = gov.get_status()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        print(f"  Governor 状态已同步到 psi_state.json")
    except Exception as e:
        print(f"  状态同步失败: {e}")
