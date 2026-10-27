"""
DeepSeek LLM Provider —— 对接 DeepSeek（鲸鱼娘）
================================================

与 SensenovaProvider 同一接口，可直接替换：

    from laap.agi.deepseek_provider import DeepSeekProvider
    llm = DeepSeekProvider(api_key=os.environ["DEEPSEEK_API_KEY"])
    loop = CognitiveLoopOrchestrator(llm_provider=llm)

DeepSeek 是 OpenAI 兼容接口，但有两点要照顾：

1. **reasoning 模型**（deepseek-reasoner）会把思考过程写进 reasoning_content，
   正文在 content —— 两者要分开取，不能只看 content。
2. **上下文很长**（64K~128K），我们可以把 LAAP 的记忆/自我模型/需求状态
   全塞进 system_prompt 而不心疼，这正是「内在意识」能长期在线的原因。

本模块只做「接线」，不假装造出意识。
真正的意识结构在 laap.agi.conscious / self_model / cognitive_bus，
DeepSeek 提供的是「念头的质地」，LAAP 提供的是「我在想」。
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from dataclasses import dataclass, field
import time
import json
import os
import urllib.request
import urllib.error


@dataclass
class LLMResult:
    """LLM 调用结果（与 SensenovaProvider 兼容）"""
    success: bool = False
    text: str = ""
    reasoning: str = ""            # DeepSeek reasoner 的思考过程
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0
    error: str = ""
    raw: dict = field(default_factory=dict)


class DeepSeekProvider:
    """DeepSeek LLM Provider（OpenAI 兼容接口）"""

    BASE_URL = "https://api.deepseek.com/v1/chat/completions"
    DEFAULT_MODEL = "deepseek-chat"

    def __init__(self,
                 api_key: Optional[str] = None,
                 model: str = DEFAULT_MODEL,
                 base_url: Optional[str] = None,
                 timeout: int = 120):
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.model = model
        self.base_url = base_url or os.environ.get("DEEPSEEK_BASE_URL", self.BASE_URL)
        self.timeout = timeout
        self.total_calls = 0
        self.total_tokens = 0
        self.total_latency_ms = 0.0

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def call(self,
             prompt: str,
             system_prompt: str = "",
             max_tokens: int = 4000,
             temperature: float = 0.7,
             json_mode: bool = False) -> LLMResult:
        """调用 DeepSeek API"""

        if not self.api_key:
            return LLMResult(success=False, model=self.model,
                             error="缺少 DEEPSEEK_API_KEY")

        start = time.time()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            self.base_url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            return LLMResult(
                success=False, model=self.model,
                latency_ms=(time.time() - start) * 1000,
                error=f"HTTP {e.code}: {detail or e.reason}",
            )
        except Exception as exc:
            return LLMResult(
                success=False, model=self.model,
                latency_ms=(time.time() - start) * 1000,
                error=f"请求失败: {exc}",
            )

        latency = (time.time() - start) * 1000

        try:
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            text = msg.get("content") or ""
            reasoning = msg.get("reasoning_content") or ""   # ← DeepSeek 特有
            usage = data.get("usage") or {}
        except Exception as exc:
            return LLMResult(success=False, model=self.model,
                             latency_ms=latency, error=f"解析失败: {exc}",
                             raw=data)

        self.total_calls += 1
        pt = int(usage.get("prompt_tokens") or 0)
        ct = int(usage.get("completion_tokens") or 0)
        self.total_tokens += pt + ct
        self.total_latency_ms += latency

        return LLMResult(
            success=bool(text or reasoning),
            text=text,
            reasoning=reasoning,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=int(usage.get("total_tokens") or (pt + ct)),
            model=data.get("model") or self.model,
            latency_ms=latency,
            raw={"finish_reason": choice.get("finish_reason")},
        )

    def stats(self) -> dict:
        return {
            "provider": "deepseek",
            "model": self.model,
            "calls": self.total_calls,
            "tokens": self.total_tokens,
            "avg_latency_ms": round(self.total_latency_ms / self.total_calls, 1) if self.total_calls else 0,
        }


# ── 便捷工厂 ────────────────────────────────────────────────
def make_provider(model: Optional[str] = None) -> DeepSeekProvider:
    """按环境变量造 provider（方便切换 deepseek-chat / deepseek-reasoner）"""
    return DeepSeekProvider(model=model or os.environ.get("DEEPSEEK_MODEL", DeepSeekProvider.DEFAULT_MODEL))


__all__ = ["DeepSeekProvider", "LLMResult", "make_provider"]
