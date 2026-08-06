"""
LAAP DeepSeek LLM Provider

直接集成DeepSeek API，绕过Hermes依赖，让LAAP Harness可以直接调用LLM。
"""

from __future__ import annotations

import time
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class LLMResult:
    """LLM调用结果"""
    success: bool = False
    text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0
    error: str = ""


class DeepSeekProvider:
    """DeepSeek LLM Provider"""
    
    def __init__(self, api_key: str, model: str = "deepseek-v4-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.deepseek.com"
        self._client = None
        self.total_calls = 0
        self.total_tokens = 0
        self.total_latency_ms = 0.0
    
    def initialize(self):
        """初始化客户端"""
        try:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
            return True
        except ImportError:
            return False
    
    def call(self, prompt: str, system_prompt: str = "", 
             max_tokens: int = 3000, temperature: float = 0.7) -> LLMResult:
        """调用DeepSeek API"""
        start_time = time.time()
        
        if not self._client:
            return LLMResult(
                success=False,
                error="Client not initialized",
                latency_ms=(time.time() - start_time) * 1000
            )
        
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=False
            )
            
            latency_ms = (time.time() - start_time) * 1000
            usage = response.usage
            
            self.total_calls += 1
            self.total_tokens += usage.total_tokens
            self.total_latency_ms += latency_ms
            
            return LLMResult(
                success=True,
                text=response.choices[0].message.content,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                model=self.model,
                latency_ms=latency_ms
            )
        except Exception as e:
            return LLMResult(
                success=False,
                error=str(e),
                latency_ms=(time.time() - start_time) * 1000
            )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_calls": self.total_calls,
            "total_tokens": self.total_tokens,
            "avg_latency_ms": round(self.total_latency_ms / max(self.total_calls, 1), 2),
            "model": self.model,
        }


class LAAPLLMIntegration:
    """LAAP LLM集成层"""
    
    def __init__(self, provider: Any):
        self.provider = provider
        self._initialized = False
    
    def initialize(self) -> bool:
        """初始化LLM提供者"""
        self._initialized = self.provider.initialize()
        return self._initialized
    
    def llm_call(self, prompt: str, system_prompt: str = "",
                 max_tokens: int = 3000) -> Dict[str, Any]:
        """调用LLM"""
        if not self._initialized:
            return {"success": False, "error": "LLM not initialized"}
        
        result = self.provider.call(prompt, system_prompt, max_tokens)
        
        if result.success:
            return {
                "success": True,
                "text": result.text,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
                "latency_ms": result.latency_ms,
                "model": result.model,
            }
        else:
            return {"success": False, "error": result.error}
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.provider.get_stats()


def create_deepseek_integration(api_key: str) -> LAAPLLMIntegration:
    """创建DeepSeek集成"""
    provider = DeepSeekProvider(api_key)
    return LAAPLLMIntegration(provider)