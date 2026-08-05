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
        if start != -1 and end > start:
            data = json.loads(text[start : end + 1])
        else:
            raise LLMError(f"{what}不是合法 JSON")
    if not isinstance(data, dict):
        raise LLMError(f"{what}不是 JSON 对象")
    return data