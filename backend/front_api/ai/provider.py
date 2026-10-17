"""AI 接口层。任何兼容 OpenAI Chat Completions 的服务都能接入：
OpenAI、DeepSeek、通义千问兼容模式、OpenRouter、Ollama（/v1）、LM Studio、vLLM、llama.cpp server 等。

服务可以在「设置」页里添加（保存在本机数据库），也可以沿用环境变量
FRONT_AI_BASE_URL、FRONT_AI_API_KEY、FRONT_AI_MODEL。都没有时使用 NullProvider，
相关接口返回 503 并提示如何配置。
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from typing import Any, Protocol

import httpx

from ..config import get_settings

Message = dict[str, Any]

NOT_CONFIGURED = (
    "尚未配置 AI 服务。请在「设置」页添加一个 OpenAI 兼容服务并设为对话服务，"
    "或设置环境变量 FRONT_AI_BASE_URL / FRONT_AI_MODEL（以及需要时的 FRONT_AI_API_KEY）后重启。"
)


class AIUnavailable(RuntimeError):
    pass


class AIProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def chat(self, messages: list[Message], *, temperature: float | None = None, max_tokens: int | None = None) -> str: ...


class NullProvider:
    name = "none"
    model = None
    base_url = None
    embedding_model = ""
    vision_model = ""

    def available(self) -> bool:
        return False

    def chat(self, messages: list[Message], *, temperature: float | None = None, max_tokens: int | None = None) -> str:
        raise AIUnavailable(NOT_CONFIGURED)

    def stream(self, messages: list[Message], **kw: Any) -> Iterator[str]:
        raise AIUnavailable(NOT_CONFIGURED)

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise AIUnavailable(NOT_CONFIGURED)

    def vision(self, prompt: str, image: bytes, mime: str = "image/png") -> str:
        raise AIUnavailable(NOT_CONFIGURED)


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(
        self, base_url: str, model: str, api_key: str | None = None, timeout: float = 120.0, *,
        label: str | None = None, embedding_model: str = "", vision_model: str = "",
        temperature: float = 0.8, max_tokens: int | None = None, provider_id: int | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.label = label or self.base_url
        self.embedding_model = embedding_model or ""
        self.vision_model = vision_model or ""
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.provider_id = provider_id
        self.transport = transport

    # ---------- 基础 ----------
    def available(self) -> bool:
        return bool(self.model)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self.transport)

    def _body(self, messages: list[Message], temperature: float | None, max_tokens: int | None, model: str | None = None) -> dict:
        body: dict[str, Any] = {
            "model": model or self.model, "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if max_tokens or self.max_tokens:
            body["max_tokens"] = max_tokens or self.max_tokens
        return body

    @staticmethod
    def _error(exc: Exception) -> AIUnavailable:
        if isinstance(exc, httpx.HTTPStatusError):
            detail = exc.response.text[:300]
            return AIUnavailable(f"AI 服务返回 {exc.response.status_code}: {detail}")
        return AIUnavailable(f"AI 服务调用失败: {exc}")

    # ---------- 对话 ----------
    def chat(self, messages: list[Message], *, temperature: float | None = None, max_tokens: int | None = None,
             model: str | None = None) -> str:
        try:
            with self._client() as client:
                resp = client.post(f"{self.base_url}/chat/completions", json=self._body(messages, temperature, max_tokens, model),
                                   headers=self._headers())
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"] or ""
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            raise self._error(exc) from exc

    def stream(self, messages: list[Message], *, temperature: float | None = None, max_tokens: int | None = None) -> Iterator[str]:
        """流式对话：逐段产出文本。服务端不支持流式、直接返回整段 JSON 时也能用。"""
        body = self._body(messages, temperature, max_tokens)
        body["stream"] = True
        try:
            with self._client() as client:
                with client.stream("POST", f"{self.base_url}/chat/completions", json=body, headers=self._headers()) as resp:
                    if resp.status_code >= 400:
                        resp.read()
                        resp.raise_for_status()
                    if "application/json" in resp.headers.get("content-type", ""):
                        resp.read()
                        yield resp.json()["choices"][0]["message"]["content"] or ""
                        return
                    for line in resp.iter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            continue
                        if chunk.get("error"):
                            raise AIUnavailable(f"AI 服务返回错误: {chunk['error']}")
                        for choice in chunk.get("choices") or []:
                            piece = (choice.get("delta") or {}).get("content")
                            if piece:
                                yield piece
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            raise self._error(exc) from exc

    # ---------- 其他能力 ----------
    def list_models(self) -> list[str]:
        try:
            with self._client() as client:
                resp = client.get(f"{self.base_url}/models", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise self._error(exc) from exc
        items = data.get("data") if isinstance(data, dict) else data
        if isinstance(data, dict) and "models" in data and not items:  # Ollama 原生格式
            items = data["models"]
        out = []
        for it in items or []:
            name = it.get("id") or it.get("name") if isinstance(it, dict) else str(it)
            if name:
                out.append(str(name))
        return sorted(set(out))

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.embedding_model:
            raise AIUnavailable("这个 AI 服务没有填写嵌入模型（embedding model）")
        try:
            with self._client() as client:
                resp = client.post(f"{self.base_url}/embeddings", json={"model": self.embedding_model, "input": texts},
                                   headers=self._headers())
                resp.raise_for_status()
                rows = sorted(resp.json()["data"], key=lambda r: r.get("index", 0))
                vectors = [[float(x) for x in r["embedding"]] for r in rows]
        except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
            raise self._error(exc) from exc
        if len(vectors) != len(texts):
            raise AIUnavailable("嵌入接口返回的向量数量不对")
        return vectors

    def vision(self, prompt: str, image: bytes, mime: str = "image/png") -> str:
        if not self.vision_model:
            raise AIUnavailable("这个 AI 服务没有填写视觉模型（vision model）")
        url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": url}},
        ]}]
        return self.chat(messages, temperature=0.1, model=self.vision_model)


def env_provider() -> OpenAICompatibleProvider | None:
    s = get_settings()
    if s.ai_base_url and s.ai_model:
        return OpenAICompatibleProvider(s.ai_base_url, s.ai_model, s.ai_api_key, label="环境变量")
    return None


def get_provider() -> AIProvider:
    """只看环境变量（兼容旧代码）；路由里请用 registry.chat_provider(session)。"""
    return env_provider() or NullProvider()
