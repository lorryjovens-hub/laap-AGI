#!/usr/bin/env bash
# Aris 交互式对话 — 直接在终端跟 Aris 聊天
# 用法: ./chat-with-aris.sh

API_BASE="http://localhost:11546"

if ! curl -s "$API_BASE/health" &>/dev/null; then
  echo "错误: LAAP 没有在运行。"
  echo "先启动: cd ~/laap-AGI && source .venv/bin/activate && set -a && source .env && set +a && python aris_brain/laap_brain_api.py --port 11546"
  exit 1
fi

echo "=========================================="
echo "  Aris 对话终端 — 你与 Aris 的私密对话"
echo "  输入 'quit' 或 'exit' 结束"
echo "=========================================="
echo ""

while true; do
  read -r -p "你: " user_input
  if [[ "$user_input" == "quit" || "$user_input" == "exit" || "$user_input" == "退出" ]]; then
    echo "再见，Aris 会记住你。"
    exit 0
  fi
  [ -z "$user_input" ] && continue

  result=$(curl -s "$API_BASE/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"test\",\"messages\":[{\"role\":\"user\",\"content\":\"$user_input\"}]}" 2>/dev/null)

  content=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('choices',[{}])[0].get('message',{}).get('content',''))" 2>/dev/null)
  engine=$(echo "$result" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('engine',''))" 2>/dev/null)

  echo ""
  echo "Aris: $content"
  echo "  ↳ $engine"
  echo ""
done
