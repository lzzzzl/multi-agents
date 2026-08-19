"""LLM Provider 抽象基类。"""

from abc import ABC, abstractmethod
from collections.abc import Callable

from app.llms.types import LLMMessage, LLMResult


class LLMProvider(ABC):
    """任何模型供应商都应实现 chat 接口,返回统一 LLMResult。

    Step 2.3 流式支持:调用方传入 on_token 回调时,Provider 在产出
    token 增量的同时回调(chunk 为文本片段),最终仍返回完整 LLMResult,
    与非流式路径保持同一契约,便于上层(重试/事件)复用。
    """

    model: str

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> LLMResult:
        """根据消息列表返回模型回复;提供 on_token 时按增量回调输出。"""
        raise NotImplementedError
