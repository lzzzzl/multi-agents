"""Agent 输出 JSON 解析工具(容忍 ```json 包裹与多余文字)。"""

import json

from app.llms import LLMError


def load_json(content: str, *, what: str = "Agent 输出") -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text[text.find("\n") + 1 :]
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"{what}不是合法 JSON", code="LLM_JSON_PARSE")
        text = text[start : end + 1]
        # 大模型常把字符串值内的换行/回车写成裸字符,导致 JSON 非法。
        # 转为合法转义序列后再尝试解析。
        try:
            data = json.loads(_escape_string_newlines(text))
        except json.JSONDecodeError as exc:
            raise LLMError(f"{what}不是合法 JSON", code="LLM_JSON_PARSE") from exc
    if not isinstance(data, dict):
        raise LLMError(f"{what}不是 JSON 对象", code="LLM_JSON_PARSE")
    return data


def _escape_string_newlines(text: str) -> str:
    """把 JSON 字符串值内未转义的换行/回车替换为 \\n,使其可被 json 解析。"""
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\":
            out.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if in_string and ch in "\r\n":
            out.append("\\n")
            continue
        out.append(ch)
    return "".join(out)
