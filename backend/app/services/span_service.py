"""LLM span 记录助手(Step 0.3 轻量 trace)。

workflow 在每次 LLM 调用(含重试的每次尝试)后调用 record_llm_span,
把 model/tokens/latency/status/error_code 落到 llm_spans 表,
供结构化查询与后续 trace UI 使用。
"""

from sqlalchemy.orm import Session

from app.models import LlmSpan


def record_llm_span(
    db: Session,
    run_id: str,
    *,
    step_id: str | None,
    agent_id: str | None,
    model: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    status: str,
    attempt: int = 1,
    error_code: str | None = None,
    error_message: str | None = None,
) -> LlmSpan:
    """记录一次 LLM 调用 span。status 取 success / failed。"""
    span = LlmSpan(
        run_id=run_id,
        step_id=step_id,
        agent_id=agent_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        status=status,
        attempt=attempt,
        error_code=error_code,
        error_message=error_message,
    )
    db.add(span)
    db.commit()
    db.refresh(span)
    return span
