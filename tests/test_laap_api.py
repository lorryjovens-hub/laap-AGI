"""
LAAP Brain API 端到端测试
==========================

验证 API 服务器能启动并响应核心端点。
运行:
    python -m pytest tests/test_laap_api.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the repository root is on sys.path when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from aiohttp.test_utils import TestClient, TestServer

from laap_brain.api import create_app


@pytest.mark.asyncio
async def test_health_endpoint():
    """/health 应返回 200 和 status=ok。"""
    app = create_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.get("/health")
        assert resp.status == 200
        data = await resp.json()
        assert data.get("status") == "ok"
        assert "version" in data
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_root_endpoint():
    """/ 应返回 API 元信息和端点列表。"""
    app = create_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.get("/")
        assert resp.status == 200
        data = await resp.json()
        assert data.get("name") == "LAAP Brain API"
        assert "/health" in data.get("endpoints", {})
        assert "/v1/cognitive_state" in data.get("endpoints", {})
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cognitive_state_endpoint():
    """/v1/cognitive_state 应能接收输入并返回状态或优雅降级错误。"""
    app = create_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.post("/v1/cognitive_state", json={"input": "Hello Aris"})
        # PSI adapter 可能不可用，但至少不应抛未处理异常
        assert resp.status in (200, 503, 500)
        data = await resp.json()
        assert "state" in data
        assert "preamble" in data
        assert "cot_hint" in data
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_chat_completions_openai_compatible():
    """/v1/chat/completions 应返回 OpenAI-compatible 结构。"""
    app = create_app()
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        resp = await client.post(
            "/v1/chat/completions",
            json={
                "model": "laap-core",
                "messages": [{"role": "user", "content": "你好"}],
            },
        )
        assert resp.status in (200, 500)
        data = await resp.json()
        if resp.status == 200:
            assert "choices" in data
            assert data.get("object") == "chat.completion"
        else:
            assert "error" in data
    finally:
        await client.close()
