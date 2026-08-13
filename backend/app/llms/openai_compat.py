"""OpenAI 兼容协议的 LLM Provider(适用于 DeepSeek / 通义 / 智谱 / Ollama 等)。"""

import json
import logging
import time

import httpx

from app.core.config import settings
from app.llms.base import LLMProvider
from app.llms.types import LLMError, LLMMessage, LLMResult, LLMUsage

logger = logging.getLogger(__name__)


class OpenAICompatProvider(LLMProvider):
    """通过 OpenAI 兼容的 /chat/completions 接口调用模型。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
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
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM 请求失败: {exc}", code="LLM_TIMEOUT") from exc

        latency_ms = int((time.monotonic() - started) * 1000)

        if resp.status_code != 200:
            detail = resp.text[:500]
            logger.error("LLM returned %s: %s", resp.status_code, detail)
            raise LLMError(
                f"LLM 返回 {resp.status_code}: {detail}",
                status_code=resp.status_code,
                code="LLM_HTTP_ERROR",
            )

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise LLMError("LLM 返回非 JSON 响应", code="LLM_JSON_PARSE") from exc

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
            latency_ms=latency_ms,
            raw=data,
        )


def from_settings() -> OpenAICompatProvider:
    return OpenAICompatProvider(
        api_key=settings.effective_llm_api_key,
        base_url=settings.LLM_BASE_URL,
        model=settings.effective_llm_model,
    )
