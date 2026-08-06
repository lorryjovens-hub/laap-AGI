# ── LAAP Dockerfile ──────────────────────────────────────────
# 多阶段构建: 最小运行时镜像
#
# 构建:
#   docker build -t laap-aris .
#
# 运行:
#   docker run -d --name aris \
#     -p 11546:11546 \
#     -v aris-state:/app/aris_brain/state \
#     -e DEEPSEEK_API_KEY=sk-xxx \
#     laap-aris
#
# ═════════════════════════════════════════════════════════════

# ── Stage 1: 基础 Python 环境 ─────────────────────────────
FROM python:3.13-slim AS base

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖声明
COPY requirements.txt pyproject.toml ./

# 安装核心依赖（忽略 optional 注释）
RUN pip install --no-cache-dir flask requests numpy aiohttp && \
    pip install --no-cache-dir -e . 2>/dev/null || true

# ── Stage 2: 生产镜像 ─────────────────────────────────────
FROM python:3.13-slim

WORKDIR /app

# 从构建阶段复制已安装的包
COPY --from=base /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=base /usr/local/bin /usr/local/bin

# 创建运行时目录
RUN mkdir -p /app/aris_brain/state /app/aris_brain/memory && \
    useradd -m -u 1001 aris && \
    chown -R aris:aris /app

# 复制 LAAP 源码
COPY --chown=aris:aris . .

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:11546/health')" || exit 1

USER aris

# 环境变量默认值
ENV LAAP_PORT=11546 \
    LAAP_API_BASE=http://localhost:11546 \
    LAAP_STATE_DIR=/app/aris_brain/state \
    PYTHONUNBUFFERED=1

EXPOSE 11546

# 启动 LAAP Brain API
CMD ["python", "aris_brain/laap_brain_api.py", "--port", "11546"]
