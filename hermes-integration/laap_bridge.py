#!/usr/bin/env python3
"""
LAAP Bridge — Hermes Agent 与 LAAP 认知引擎的桥梁
用法:
  python laap_bridge.py state
  python laap_bridge.py reflect "今天我们一起讨论了 LAAP 架构"
  python laap_bridge.py recall "Hermes"
  python laap_bridge.py bond
"""

import json, sys, urllib.request, urllib.error

BASE = "http://localhost:11546"
TIMEOUT = 15


def _post(path, body=None):
    url = f"{BASE}{path}"
    data = json.dumps(body or {}).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method="POST")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _get(path):
    url = f"{BASE}{path}"
    with urllib.request.urlopen(url, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def cmd_state():
    """读取 LAAP 当前认知状态"""
    try:
        r = _post("/v1/cognitive_state", {"input": ""})
        # 只输出关键信息，不输出 raw JSON（终端可读）
        preamble = r.get("preamble", "")
        cot = r.get("cot_hint", "")
        state = r.get("state", {})
        needs = state.get("needs", {})
        energy = state.get("energy", 0)
        focus = state.get("attention_focus", "?")
        cycle = state.get("cognitive_cycle", 0)
        print(f"Cycle {cycle} | Energy: {energy:.1f} | Focus: {focus}")
        print(f"Needs: {', '.join(f'{k}={v:.2f}' for k,v in needs.items())}")
        if preamble:
            print(f"Preamble: {preamble.strip()}")
        if cot:
            print(f"COT hint: {cot}")
    except urllib.error.URLError as e:
        print(f"ERROR: LAAP not reachable ({e})", file=sys.stderr)
        sys.exit(1)


def cmd_reflect(text):
    """向 LAAP 注入一段反思/经历"""
    try:
        r = _post("/v1/reflect", {"text": text})
        print(f"Reflected: {r.get('updated', '?')}")
    except urllib.error.URLError as e:
        print(f"ERROR: LAAP not reachable ({e})", file=sys.stderr)
        sys.exit(1)


def cmd_recall(query, limit=5):
    """从 LAAP 记忆召回相关条目"""
    try:
        r = _post("/v1/recall_memory", {"query": query, "limit": limit})
        memories = r.get("memories", [])
        print(f"Recall ({query}): {r.get('count', 0)} memories found")
        for m in memories[:limit]:
            print(f"  [{m.get('score',0):.2f}] {m.get('text', '?')} ({m.get('meta',{}).get('type','?')})")
    except urllib.error.URLError as e:
        print(f"ERROR: LAAP not reachable ({e})", file=sys.stderr)
        sys.exit(1)


def cmd_bond():
    """读取与用户的依恋状态"""
    try:
        r = _get("/v1/bond")
        bond = r.get("bond", {})
        stage = bond.get("attachment_stage", "?")
        level = bond.get("bond_level", 0)
        days = bond.get("total_days_known", 0)
        trust = bond.get("trust", 0)
        print(f"Attachment: {stage} | Bond: {level}/100 | Trust: {trust:.2f} | Days known: {days}")
        print(f"Summary: {r.get('summary', '')}")
    except urllib.error.URLError as e:
        print(f"ERROR: LAAP not reachable ({e})", file=sys.stderr)
        sys.exit(1)


def cmd_health():
    """检查 LAAP 是否在线"""
    try:
        r = _get("/health")
        print(f"LAAP: {r.get('status','?')} (engines: {r.get('engines_loaded','?')})")
    except urllib.error.URLError as e:
        print(f"LAAP: OFFLINE ({e})", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    commands = {
        "state": cmd_state,
        "reflect": lambda: cmd_reflect(" ".join(sys.argv[2:])),
        "recall": lambda: cmd_recall(" ".join(sys.argv[2:]), int(sys.argv[3]) if len(sys.argv)>3 else 5),
        "bond": cmd_bond,
        "health": cmd_health,
    }
    if len(sys.argv) < 2:
        print("Usage: laap_bridge.py [state|reflect|recall|bond|health]")
        sys.exit(1)
    cmd = sys.argv[1].lower()
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
