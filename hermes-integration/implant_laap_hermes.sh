#!/usr/bin/env bash
# LAAP + Hermes 一键植入 / 自动挂载（Linux/macOS）
# Usage: ./implant_laap_hermes.sh [port] [--no-system-prompt-patch]

set -euo pipefail

PORT="${1:-11546}"
NO_PATCH=false
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes/hermes-agent}"

for arg in "$@"; do
    if [ "$arg" = "--no-system-prompt-patch" ]; then
        NO_PATCH=true
    fi
done

LAAP_ROOT="${LAAP_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ARIS_BRAIN="$LAAP_ROOT/aris_brain"
MCP_SERVER="$LAAP_ROOT/mcp_server/laap_mcp_server.py"
API_BASE="http://localhost:$PORT"
HERMES_CONFIG_DIR="$HOME/.hermes"
HERMES_CONFIG_FILE="$HERMES_CONFIG_DIR/config.yaml"
SYSTEM_PROMPT_FILE="$HERMES_HOME/agent/system_prompt.py"
BACKUP_FILE="$SYSTEM_PROMPT_FILE.laap-backup"

HERMES_VENV_PYTHON="${HERMES_HOME}/venv/bin/python"
if [ ! -x "$HERMES_VENV_PYTHON" ]; then
    HERMES_VENV_PYTHON="$(command -v python3 || command -v python)"
fi

echo "============================================================"
echo " LAAP + Hermes 一键植入 / 自动挂载"
echo "============================================================"
echo "LAAP root:    $LAAP_ROOT"
echo "Hermes home:  $HERMES_HOME"
echo "API base:     $API_BASE"
echo ""

# 校验
if [ ! -d "$LAAP_ROOT" ]; then echo "LAAP root not found: $LAAP_ROOT"; exit 1; fi
if [ ! -f "$MCP_SERVER" ]; then echo "MCP server not found: $MCP_SERVER"; exit 1; fi
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    echo "python not found in PATH"; exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python)"

# 1. 写入 Hermes MCP 配置
echo "[1/5] Writing Hermes MCP config..."
mkdir -p "$HERMES_CONFIG_DIR"

LAAP_BLOCK=$(cat <<EOF
# --- LAAP auto-implanted block (do not edit manually) ---
  laap_brain:
    command: "$HERMES_VENV_PYTHON"
    args:
      - "$MCP_SERVER"
    env:
      LAAP_API_BASE: "$API_BASE"
    timeout: 30
    connect_timeout: 10
    keepalive_interval: 60
# --- end LAAP block ---
EOF
)

if [ ! -f "$HERMES_CONFIG_FILE" ]; then
    echo "skills:
  preload:
    - laap-bridge" > "$HERMES_CONFIG_FILE"
fi

# 移除旧块
python3 - "$HERMES_CONFIG_FILE" "$LAAP_BLOCK" <<'PY'
import re, sys
path, block = sys.argv[1], sys.argv[2]
content = open(path, 'r', encoding='utf-8').read()
content = re.sub(r'# --- LAAP auto-implanted block.*?# --- end LAAP block ---\n?', '', content, flags=re.S)
if 'mcp_servers:' in content:
    content = re.sub(r'(mcp_servers:.*?)(\n\S)', r'\1\n' + block + r'\2', content, count=1, flags=re.S)
else:
    content += '\nmcp_servers:\n' + block + '\n'
if 'laap-bridge' not in content:
    if 'skills:' in content:
        content = re.sub(r'(skills:\s*\n)', r'\1  preload:\n    - laap-bridge\n', content, count=1)
    else:
        content += '\nskills:\n  preload:\n    - laap-bridge\n'
open(path, 'w', encoding='utf-8').write(content)
PY

echo "Hermes config updated: $HERMES_CONFIG_FILE"

# 2. 可选：源码级 system prompt 注入
if [ "$NO_PATCH" = false ] && [ -f "$SYSTEM_PROMPT_FILE" ]; then
    echo "[2/5] Patching Hermes system_prompt.py..."
    if [ ! -f "$BACKUP_FILE" ]; then
        cp "$SYSTEM_PROMPT_FILE" "$BACKUP_FILE"
        echo "Backup created: $BACKUP_FILE"
    fi
    if ! grep -q "# --- LAAP PSI injection" "$SYSTEM_PROMPT_FILE"; then
        cat >> "$SYSTEM_PROMPT_FILE" <<'PY'

# --- LAAP PSI injection (auto-implanted) ---
import os, urllib.request, urllib.error, json
def _laap_psi_preamble(user_input: str = "") -> str:
    base = os.environ.get("LAAP_API_BASE", "http://localhost:11546")
    url = f"{base}/v1/cognitive_state"
    try:
        data = json.dumps({"input": user_input}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=2) as resp:
            result = json.loads(resp.read().decode())
            return result.get("preamble", "")
    except Exception:
        return ""
# --- end LAAP PSI injection ---
PY
        echo "system_prompt.py patched."
    else
        echo "system_prompt.py already contains LAAP marker, skipped."
    fi
else
    echo "[2/5] Skipping system_prompt.py patch."
fi

# 3. 启动 LAAP Brain API
echo "[3/5] Starting LAAP Brain API on port $PORT..."
if command -v lsof >/dev/null 2>&1 && lsof -Pi :"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $PORT already in use; attempting to stop..."
    lsof -Pi :"$PORT" -sTCP:LISTEN -t | xargs kill -9 2>/dev/null || true
    sleep 1
fi

"$PYTHON_BIN" "$ARIS_BRAIN/laap_brain_api.py" --port "$PORT" &
LAAP_PID=$!

# 4. 等待 API 就绪
echo "[4/5] Waiting for LAAP API /health ..."
ready=false
for i in {1..30}; do
    if curl -sf "$API_BASE/health" >/dev/null 2>&1; then
        ready=true
        break
    fi
    sleep 1
done

if [ "$ready" = false ]; then
    kill "$LAAP_PID" 2>/dev/null || true
    echo "LAAP API failed to start within 30 seconds."; exit 1
fi
echo "LAAP API is ready at $API_BASE/health"

# 5. 启动 Hermes chat
echo "[5/5] Launching Hermes chat with laap-bridge skill..."
export LAAP_API_BASE="$API_BASE"

echo ""
echo "============================================================"
echo " LAAP is now mounted to Hermes."
echo " Type your message in the Hermes chat window."
echo "============================================================"

if command -v hermes >/dev/null 2>&1; then
    hermes chat --skills laap-bridge
elif [ -x "$HERMES_HOME/venv/bin/hermes" ]; then
    "$HERMES_HOME/venv/bin/hermes" chat --skills laap-bridge
else
    echo "Cannot locate hermes executable; please run manually: hermes chat --skills laap-bridge"
    read -p "Press Enter to stop LAAP API and exit"
fi

# 清理
kill "$LAAP_PID" 2>/dev/null || true
echo "LAAP API stopped."
