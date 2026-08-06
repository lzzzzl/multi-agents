"""Tool Registry:注册与查找工具。"""

from app.tools.base import Tool, ToolError


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool {tool.name!r} 已注册")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        tool = self._tools.get(name)
        if not tool:
            raise ToolError(f"未知工具: {name}", code="TOOL_NOT_FOUND")
        return tool

    def has(self, name: str) -> bool:
        return name in self._tools

    def list(self) -> list[Tool]:
        return list(self._tools.values())


_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """全局 Tool Registry 单例。首次调用时注册内置工具。"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        from app.tools.builtin import register_builtins

        register_builtins(_registry)
    return _registry