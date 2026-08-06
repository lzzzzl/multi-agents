"""内置低风险工具。

当前实现为本地确定性工具,供 Agent 调用演示 Tool 系统链路:
- current_time: 返回当前时间
- generate_report: 依据任务标题生成结构化初稿(mock 数据,无需外部服务)
"""

from datetime import datetime, timezone

from app.tools.base import SAFE, Tool, ToolError, ToolResult
from app.tools.registry import ToolRegistry


class CurrentTimeTool(Tool):
    name = "current_time"
    description = "返回当前 UTC 时间。"
    risk_level = SAFE
    input_schema = {"type": "object", "properties": {}, "additionalProperties": False}

    def execute(self, args: dict) -> ToolResult:
        now = datetime.now(timezone.utc)
        iso = now.isoformat()
        return ToolResult(output={"iso": iso, "utc": now.strftime("%Y-%m-%d %H:%M:%S")}, display=iso)


class GenerateReportTool(Tool):
    name = "generate_report"
    description = "根据任务标题生成一份结构化 Markdown 报告初稿(本地模拟,无外部依赖)。"
    risk_level = SAFE
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "报告标题"},
            "outline": {"type": "array", "items": {"type": "string"}, "description": "章节大纲"},
        },
        "required": ["title"],
        "additionalProperties": False,
    }

    def execute(self, args: dict) -> ToolResult:
        title = str(args.get("title") or "未命名报告")
        outline = args.get("outline") or []
        if not isinstance(outline, list):
            raise ToolError("outline 必须是字符串数组", code="INVALID_INPUT")

        outline = [str(s) for s in outline if str(s).strip()]
        sections = "\n\n".join(f"## {s}\n\n(章节内容占位)" for s in outline)
        markdown = f"# {title}\n\n## 概述\n\n本报告由 generate_report 工具生成初稿。\n\n{sections}"

        return ToolResult(
            output={"title": title, "sections": len(outline), "length": len(markdown)},
            display=markdown,
        )


def register_builtins(registry: ToolRegistry) -> None:
    registry.register(CurrentTimeTool())
    registry.register(GenerateReportTool())