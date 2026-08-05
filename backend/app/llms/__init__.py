"""LLM Provider 抽象与工厂。

通过 settings.LLM_PROVIDER 切换:
- mock   : 本地兜底,无需 API Key(默认,方便无 key 跑通流程)
- 其他    : 走 OpenAI 兼容协议(DeepSeek / 通义 / Ollama 等)
"""

import logging

from app.core.config import settings
from app.llms.base import LLMProvider
from app.llms.mock import MockLLMProvider
from app.llms.openai_compat import OpenAICompatProvider
from app.llms.types import LLMError, LLMMessage, LLMResult, LLMUsage

logger = logging.getLogger(__name__)


def get_llm_provider() -> LLMProvider:
    """根据配置返回 LLM Provider 单例(每次调用新建,保持无状态)。"""
    provider = settings.LLM_PROVIDER.strip().lower()
    if provider in {"mock", "local", "fake"}:
        return MockLLMProvider()
    if provider in {"deepseek", "openai", "dashscope", "zhipu", "ollama", "openai_compat"}:
        return OpenAICompatProvider(
            api_key=settings.effective_llm_api_key,
            base_url=settings.LLM_BASE_URL,
            model=settings.effective_llm_model,
        )
    # 未知 provider 时回退 mock,避免直接崩溃
    logger.warning("未知 LLM_PROVIDER=%r,回退到 mock", settings.LLM_PROVIDER)
    return MockLLMProvider()


__all__ = [
    "LLMProvider",
    "MockLLMProvider",
    "OpenAICompatProvider",
    "LLMError",
    "LLMMessage",
    "LLMResult",
    "LLMUsage",
    "get_llm_provider",
]