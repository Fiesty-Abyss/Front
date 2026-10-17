"""AI 接口层。任何兼容 OpenAI Chat Completions 的服务都能接入：
OpenAI、DeepSeek、通义千问兼容模式、Ollama（/v1）、LM Studio、vLLM、llama.cpp server 等。

通过环境变量配置：FRONT_AI_BASE_URL、FRONT_AI_API_KEY、FRONT_AI_MODEL。
未配置时使用 NullProvider，相关接口返回 503 并提示如何配置。
"""

from __future__ import annotations

from typing import Protocol

import httpx

from ..config import get_settings

Message = dict[str, str]


class AIUnavailable(RuntimeError):
    pass


class AIProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def chat(self, messages: list[Message], *, temperature: float = 0.8, max_tokens: int | None = None) -> str: ...


class NullProvider:
    name = "none"

    def available(self) -> bool:
        return False

    def chat(self, messages: list[Message], *, temperature: float = 0.8, max_tokens: int | None = None) -> str:
        raise AIUnavailable(
            "尚未配置 AI 服务。请设置 FRONT_AI_BASE_URL / FRONT_AI_MODEL（以及需要时的 FRONT_AI_API_KEY）后重启。"
        )


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, model: str, api_key: str | None = None, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def available(self) -> bool:
        return True

    def chat(self, messages: list[Message], *, temperature: float = 0.8, max_tokens: int | None = None) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body: dict = {"model": self.model, "messages": messages, "temperature": temperature}
        if max_tokens:
            body["max_tokens"] = max_tokens
        try:
            resp = httpx.post(f"{self.base_url}/chat/completions", json=body, headers=headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise AIUnavailable(f"AI 服务调用失败: {exc}") from exc


def get_provider() -> AIProvider:
    s = get_settings()
    if s.ai_base_url and s.ai_model:
        return OpenAICompatibleProvider(s.ai_base_url, s.ai_model, s.ai_api_key)
    return NullProvider()
