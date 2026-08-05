"""LLM Provider 抽象基类。"""

from abc import ABC, abstractmethod

from app.llms.types import LLMMessage, LLMResult


class LLMProvider(ABC):
    """任何模型供应商都应实现 chat 接口,返回统一 LLMResult。"""

    model: str

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """根据消息列表返回模型回复。"""
        raise NotImplementedError