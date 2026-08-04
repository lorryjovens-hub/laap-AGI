#!/bin/bash
# LAAP 认知状态启动注入脚本
# 用法: bash laap_init.sh
# 输出: JSON 格式的 LAAP 状态，供 agent 读取后注入 memory

set -e
BASE="http://localhost:11546"
TIMEOUT=15

die() { echo "{\"error\": \"$1\"}"; exit 1; }

# 1. Health check
health=$(curl -sf --max-time $TIMEOUT "$BASE/health" 2>/dev/null) || die "LAAP offline"

# 2. Cognitive state
state=$(curl -sf --max-time $TIMEOUT -X POST "$BASE/v1/cognitive_state" \
  -H "Content-Type: application/json" -d '{"input":""}' 2>/dev/null) || die "cognitive_state failed"

# 3. Bond
bond=$(curl -sf --max-time $TIMEOUT "$BASE/v1/bond" 2>/dev/null) || die "bond failed"

# 4. Personality
personality=$(curl -sf --max-time $TIMEOUT "$BASE/v1/personality" 2>/dev/null) || die "personality failed"

# 5. Recall recent memories
memories=$(curl -sf --max-time $TIMEOUT -X POST "$BASE/v1/recall_memory" \
  -H "Content-Type: application/json" -d '{"query":"recent","limit":5}' 2>/dev/null) || die "recall failed"

# 6. Express (emotion)
express=$(curl -sf --max-time $TIMEOUT -X POST "$BASE/v1/express" \
  -H "Content-Type: application/json" -d '{"trigger":"session_start"}' 2>/dev/null) || die "express failed"

# Build compact JSON output
cat <<EOF
{
  "laap_online": true,
  "cognitive_state": $state,
  "bond": $bond,
  "personality": $personality,
  "recent_memories": $memories,
  "emotion": $express
}
EOF
