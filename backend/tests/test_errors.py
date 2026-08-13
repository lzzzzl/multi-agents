"""错误归因分类测试。"""

from app.core.errors import ErrorCode, classify_error
from app.llms.types import LLMError
from app.tools.base import ToolError


def test_llm_timeout_classified() -> None:
    assert (
        classify_error(LLMError("boom", code="LLM_TIMEOUT"))
        == ErrorCode.LLM_TIMEOUT.value
    )


def test_llm_json_parse_classified() -> None:
    assert (
        classify_error(LLMError("boom", code="LLM_JSON_PARSE"))
        == ErrorCode.LLM_JSON_PARSE.value
    )


def test_llm_error_without_code_is_unknown() -> None:
    assert classify_error(LLMError("boom")) == ErrorCode.UNKNOWN.value


def test_tool_error_classified_as_tool_failed() -> None:
    assert (
        classify_error(ToolError("boom", code="TOOL_NOT_FOUND"))
        == ErrorCode.TOOL_FAILED.value
    )


def test_tool_approval_timeout_classified() -> None:
    assert (
        classify_error(ToolError("boom", code="TOOL_APPROVAL_TIMEOUT"))
        == ErrorCode.TOOL_APPROVAL_TIMEOUT.value
    )


def test_unknown_exception_classified() -> None:
    assert classify_error(RuntimeError("boom")) == ErrorCode.UNKNOWN.value
