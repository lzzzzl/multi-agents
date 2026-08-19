"""OpenAI 兼容协议的 LLM Provider(适用于 DeepSeek / 通义 / 智谱 / Ollama 等)。"""

import json
import logging
import time
from collections.abc import Callable

import httpx

from app.core.config import settings
from app.llms.base import LLMProvider
from app.llms.types import LLMError, LLMMessage, LLMResult, LLMUsage

logger = logging.getLogger(__name__)


class OpenAICompatProvider(LLMProvider):
    """通过 OpenAI 兼容的 /chat/completions 接口调用模型。

    Step 2.3:传入 on_token 时改用 SSE 流式请求,逐 delta 回调,
    最终聚合为完整 LLMResult(与非流式契约一致)。
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # 测试注入用(httpx.MockTransport),生产为 None
        self._transport = transport

    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> LLMResult:
        if not self.api_key:
            raise LLMError(
                "未配置 LLM API Key。请在 backend/.env 中设置 LLM_API_KEY 或切换 LLM_PROVIDER=mock"
            )

        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        started = time.monotonic()
        if on_token is not None:
            return self._chat_stream(payload, headers, on_token, started)
        return self._chat_blocking(payload, headers, started)

    # ---- 非流式(原路径) ----

    def _chat_blocking(self, payload: dict, headers: dict, started: float) -> LLMResult:
        with self._client() as client:
            try:
                resp = client.post(
                    f"{self.base_url}/chat/completions", headers=headers, json=payload
                )
            except httpx.HTTPError as exc:
                raise LLMError(f"LLM 请求失败: {exc}", code="LLM_TIMEOUT") from exc

        if resp.status_code != 200:
            return self._raise_http_error(resp)

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise LLMError("LLM 返回非 JSON 响应", code="LLM_JSON_PARSE") from exc

        return self._parse_full_response(data, started)

    # ---- 流式(SSE) ----

    def _chat_stream(
        self,
        payload: dict,
        headers: dict,
        on_token: Callable[[str], None],
        started: float,
    ) -> LLMResult:
        payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
        parts: list[str] = []
        usage_raw: dict = {}

        try:
            with self._client() as client:
                with client.stream(
                    "POST", f"{self.base_url}/chat/completions", headers=headers, json=payload
                ) as resp:
                    if resp.status_code != 200:
                        resp.read()
                        return self._raise_http_error(resp)

                    for line in resp.iter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[len("data:") :].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue  # 忽略无法解析的行(如注释/心跳)
                        if isinstance(chunk.get("usage"), dict):
                            usage_raw = chunk["usage"]
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        piece = delta.get("content") or delta.get("reasoning_content") or ""
                        if piece:
                            parts.append(piece)
                            on_token(piece)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM 流式请求失败: {exc}", code="LLM_TIMEOUT") from exc

        content = "".join(parts)
        if not content:
            raise LLMError("LLM 流式响应未返回任何 content")

        latency_ms = int((time.monotonic() - started) * 1000)
        return LLMResult(
            content=content,
            usage=LLMUsage(
                input_tokens=usage_raw.get("prompt_tokens", 0),
                # 少数供应商不带 usage:按 4 字符/token 估算
                output_tokens=usage_raw.get("completion_tokens", len(content) // 4),
                model=self.model,
            ),
            latency_ms=latency_ms,
        )

    # ---- 公共辅助 ----

    def _client(self) -> httpx.Client:
        if self._transport is not None:
            return httpx.Client(timeout=self.timeout, transport=self._transport)
        return httpx.Client(timeout=self.timeout)

    def _raise_http_error(self, resp: httpx.Response) -> LLMResult:
        detail = resp.text[:500]
        logger.error("LLM returned %s: %s", resp.status_code, detail)
        raise LLMError(
            f"LLM 返回 {resp.status_code}: {detail}",
            status_code=resp.status_code,
            code="LLM_HTTP_ERROR",
        )

    def _parse_full_response(self, data: dict, started: float) -> LLMResult:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(
                "LLM 响应缺少 choices/message 字段", code="LLM_JSON_PARSE"
            ) from exc

        # 推理模型(如 deepseek-v4-flash)先输出 reasoning_content,
        # 当 token 不足时 content 可能为空,此时回退到 reasoning_content。
        content = message.get("content") or message.get("reasoning_content") or ""
        if not content:
            raise LLMError("LLM 响应 content 与 reasoning_content 均为空")

        usage = data.get("usage") or {}
        return LLMResult(
            content=content,
            usage=LLMUsage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                model=self.model,
            ),
            latency_ms=int((time.monotonic() - started) * 1000),
            raw=data,
        )


def from_settings() -> OpenAICompatProvider:
    return OpenAICompatProvider(
        api_key=settings.effective_llm_api_key,
        base_url=settings.LLM_BASE_URL,
        model=settings.effective_llm_model,
    )
