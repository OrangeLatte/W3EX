"""模型 API 客户端：OpenAI 兼容 + Anthropic 原生。

统一能力：list_models（自动识别可用模型）/ chat（对话补全）/ validate（绑定校验）。
所有请求经全局 httpx 基础设施（代理探测 / 超时 / 重试），但 LLM 调用不走 TTL 缓存。
"""

from __future__ import annotations

from typing import Any

import httpx

from w3ex.providers.http import get_client

DEFAULT_TIMEOUT = 60.0
CHAT_TIMEOUT = 180.0


class LLMError(RuntimeError):
    """模型 API 调用失败（鉴权 / 网络 / 上游错误）。"""


class LLMClient:
    """binding: {provider: openai_compatible|anthropic, base_url, api_key, model}。"""

    def __init__(
        self, provider: str, base_url: str, api_key: str, model: str | None = None
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    # ---------- headers ----------

    def _headers(self) -> dict[str, str]:
        if self.provider == "anthropic":
            return {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        return {"Authorization": f"Bearer {self.api_key}"}

    # ---------- models ----------

    async def list_models(self) -> list[str]:
        """自动识别可用模型。openai: GET /models；anthropic: GET /v1/models。"""
        path = "/v1/models" if self.provider == "anthropic" else "/models"
        client = await get_client()
        try:
            resp = await client.get(
                f"{self.base_url}{path}", headers=self._headers(), timeout=DEFAULT_TIMEOUT
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"模型列表请求失败: {exc!r}") from exc
        if resp.status_code == 401:
            raise LLMError("鉴权失败：API Key 无效")
        if resp.status_code != 200:
            raise LLMError(f"模型列表 HTTP {resp.status_code}")
        data = resp.json().get("data") or []
        ids = [m.get("id") for m in data if m.get("id")]
        return sorted(ids)

    # ---------- chat ----------

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.4,
    ):
        """SSE 流式对话（async generator，逐段 yield 文本增量）。

        仅 openai 兼容协议支持流式；anthropic 或任何异常时抛 LLMError，
        由上层回退非流式/规则引擎。
        """
        if self.provider == "anthropic":
            raise LLMError("anthropic 流式未实现")
        client = await get_client()
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            async with client.stream(
                "POST", url, headers=self._headers(), json=body, timeout=CHAT_TIMEOUT
            ) as resp:
                if resp.status_code != 200:
                    text = (await resp.aread()).decode("utf-8", "replace")[:200]
                    raise LLMError(f"对话 HTTP {resp.status_code}: {text}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    import json as _json

                    try:
                        chunk = _json.loads(payload)
                    except ValueError:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    # 推理模型（GLM/DeepSeek-R1）正文在 reasoning_content，需回退
                    piece = delta.get("content") or delta.get("reasoning_content")
                    if piece:
                        yield piece
                    # 长度截断显式告知（用户可见"输出中断"的主因之一）
                    if choice.get("finish_reason") == "length":
                        yield "\n\n[输出已达 max_tokens 上限被截断]"
        except httpx.HTTPError as exc:
            raise LLMError(f"流式请求失败: {exc!r}") from exc

    async def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.4,
        json_mode: bool = False,
    ) -> str:
        """对话补全。json_mode=True 时请求 JSON 输出（仅 openai 兼容 response_format）。"""
        client = await get_client()
        if self.provider == "anthropic":
            system = "\n".join(m["content"] for m in messages if m["role"] == "system")
            user_msgs = [m for m in messages if m["role"] != "system"]
            body: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": user_msgs,
            }
            if system:
                body["system"] = system
            url = f"{self.base_url}/v1/messages"
        else:
            body = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            url = f"{self.base_url}/chat/completions"
        try:
            resp = await client.post(url, headers=self._headers(), json=body, timeout=CHAT_TIMEOUT)
        except httpx.HTTPError as exc:
            raise LLMError(f"对话请求失败: {exc!r}") from exc
        if resp.status_code != 200:
            raise LLMError(f"对话 HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if self.provider == "anthropic":
            content = (data.get("content") or [{}])[0].get("text")
        else:
            msg = (data.get("choices") or [{}])[0].get("message", {})
            # 推理模型（GLM/DeepSeek-R1 等）max_tokens 受限时 content 可能为空，
            # 实际输出落在 reasoning_content，需回退否则误判「模型返回空内容」
            content = msg.get("content") or msg.get("reasoning_content")
        if not content:
            raise LLMError("模型返回空内容")
        text = str(content)
        if json_mode:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                text = text[start : end + 1]
        return text

    async def chat_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.4,
    ) -> dict[str, Any]:
        """Function Calling 对话（openai 兼容协议）：返回原始 message dict。

        返回 {content, tool_calls, finish_reason}——tool_calls 非空时 content 可能为空。
        anthropic 协议暂不支持工具循环，抛 LLMError 由上层回退。
        """
        if self.provider == "anthropic":
            raise LLMError("anthropic 协议暂不支持工具调用，请使用 openai_compatible")
        client = await get_client()
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=body,
            timeout=CHAT_TIMEOUT,
        )
        if resp.status_code != 200:
            raise LLMError(f"对话 HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        return {
            "content": msg.get("content") or "",
            "reasoning": msg.get("reasoning_content") or "",
            "tool_calls": msg.get("tool_calls") or [],
            "finish_reason": choice.get("finish_reason"),
        }

    # ---------- validate ----------

    async def validate(self) -> dict[str, Any]:
        """绑定校验：优先 list_models，任何列表失败（404/网关/非 JSON）都用一次 chat ping 兜底；
        鉴权失败（401/403）不兜底直接判失败。"""
        try:
            models = await self.list_models()
            return {"ok": True, "models": models, "error": None}
        except LLMError as exc:
            if "鉴权失败" in str(exc):
                return {"ok": False, "models": [], "error": str(exc)}
            try:
                await self.chat([{"role": "user", "content": "ping"}], max_tokens=64)
                return {"ok": True, "models": [], "error": None}
            except LLMError as exc2:
                return {"ok": False, "models": [], "error": str(exc2) or str(exc)}
