"""带前缀的字符串 ID 生成。例如 task_xxxx, run_xxxx, evt_xxxx。"""

import uuid


def generate_id(prefix: str) -> str:
    """生成带前缀的字符串 ID,与 API 文档示例一致(task_123 / run_123 / evt_123)。"""
    return f"{prefix}_{uuid.uuid4().hex[:24]}"
