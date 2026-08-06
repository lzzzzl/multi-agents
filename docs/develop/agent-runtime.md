# Multi Agents Agent Runtime 设计

## 1. 目标

Agent Runtime 负责把一个 Agent 从配置变成可执行单元。它需要处理输入校验、上下文构建、模型调用、结构化输出、工具调用、事件记录、失败重试和成本统计。

设计目标：

- Agent 执行过程可观测。
- Agent 输入输出有 schema 约束。
- LLM Provider 可替换。
- Tool 调用有权限和审计。
- 失败可以定位、重试和恢复。

## 2. Runtime 分层

```txt
Workflow Orchestrator
  |
  v
Agent Runtime
  |
  | build context
  | validate input
  | call model
  | parse output
  | call tools
  | emit events
  v
LLM Provider / Tool Runtime / Memory Store
```

建议模块：

```txt
backend/app/agents/
  base.py
  planner.py
  researcher.py
  writer.py
  reviewer.py
  supervisor.py

backend/app/llms/
  base.py
  openai_provider.py
  anthropic_provider.py
  local_provider.py

backend/app/runtime/
  agent_runner.py
  context_builder.py
  output_parser.py
  retry_policy.py
```

## 3. Agent 配置

Agent 配置建议包含：

```txt
id
name
role
description
system_prompt
model_provider
model_name
model_config
allowed_tools
input_schema
output_schema
memory_policy
retry_policy
```

示例：

```json
{
  "name": "planner",
  "role": "task_planning",
  "model_provider": "openai",
  "model_name": "gpt-5",
  "model_config": {
    "temperature": 0.2
  },
  "allowed_tools": [],
  "memory_policy": {
    "include_task_input": true,
    "include_previous_steps": false
  }
}
```

## 4. Agent 执行生命周期

标准生命周期：

```txt
load agent config
  -> validate input
  -> build context
  -> emit agent_started
  -> call LLM
  -> parse structured output
  -> optionally call tools
  -> validate output
  -> persist messages / events / llm_calls
  -> emit agent_completed
```

失败路径：

```txt
LLM timeout
  -> emit llm_call_failed
  -> retry if allowed
  -> emit agent_failed if exhausted
```

```txt
Invalid structured output
  -> try repair
  -> retry with validation error
  -> fail step if still invalid
```

## 5. 输入输出协议

Agent 输入应来自 workflow step，而不是直接读取全局状态。

输入示例：

```json
{
  "task": {
    "title": "生成竞品分析报告",
    "description": "分析三个竞品"
  },
  "context": {
    "previous_outputs": []
  },
  "constraints": {
    "language": "zh-CN",
    "format": "markdown"
  }
}
```

输出示例：

```json
{
  "status": "completed",
  "summary": "已生成三步执行计划",
  "data": {
    "steps": []
  },
  "artifacts": []
}
```

建议所有 Agent 输出统一包一层：

```txt
status
summary
data
tool_requests
artifacts
warnings
```

这样 workflow 可以稳定消费不同 Agent 的结果。

## 6. 结构化输出

优先使用模型原生 structured output 能力。如果模型不支持，则使用 JSON schema prompt + parser + repair。

处理策略：

- 首次要求模型按 schema 输出。
- 解析失败时记录 `invalid_output`。
- 触发一次 repair prompt。
- repair 失败则标记 step failed。

不要让下游 workflow 直接依赖自由文本。

## 7. Context Builder

Context Builder 负责决定本次 Agent 能看到什么。

输入来源：

- 当前 task input。
- 当前 run metadata。
- 前置 step output。
- 用户 message。
- 项目知识库检索结果。
- Agent 自身 memory policy。

规则：

- 默认只给 Agent 必要上下文。
- 长上下文需要压缩摘要。
- 敏感内容进入上下文前需要权限检查。
- 每次上下文构建结果需要可追踪。

## 8. LLM Provider 抽象

Provider 接口建议：

```python
class LLMProvider:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        ...

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMStreamEvent]:
        ...
```

请求字段：

```txt
model
messages
temperature
max_tokens
response_schema
tools
metadata
```

响应字段：

```txt
content
structured_output
tool_calls
input_tokens
output_tokens
duration_ms
raw_response
```

业务层不应直接调用具体模型 SDK。

## 9. Tool 调用

Agent 不能直接执行任意函数，必须通过 Tool Runtime。

调用流程：

```txt
Agent requests tool
  -> check agent permission
  -> validate input schema
  -> check risk level
  -> request approval if needed
  -> execute tool
  -> validate output schema
  -> persist tool_call
  -> emit events
```

每次 Tool 调用必须记录：

- tool name
- caller agent
- input summary
- output summary
- duration
- status
- approval status
- error

## 10. 重试策略

建议分层重试：

- LLM 网络错误：短间隔自动重试。
- 结构化输出错误：repair 一次，再重试一次。
- Tool 临时错误：按工具配置重试。
- 权限错误：不重试。
- 用户取消：不重试。

重试事件：

```txt
step_retried
llm_call_failed
tool_call_failed
agent_failed
```

## 11. 成本与限额

Runtime 需要支持：

- 单次 run token 上限。
- 单个 Agent token 上限。
- 单个 Tool 时间上限。
- 单个 workflow 最大 step 数。
- 单次 run 最大费用估算。

超过限制时：

- 写入 `run_event`。
- 停止或暂停 run。
- 给前端明确错误原因。

## 12. MVP Agent

第一版建议实现：

- `PlannerAgent`：输出结构化 plan。
- `WriterAgent`：生成 Markdown artifact。
- `ReviewerAgent`：检查输出质量。

第二阶段实现：

- `ResearcherAgent`
- `SupervisorAgent`
- `SynthesizerAgent`

## 13. 验收标准

- Agent 可以独立单元测试。
- Agent 输入输出都能 schema 校验。
- 每次 LLM 调用都有记录。
- Agent 失败时能定位到 step、message、llm_call 或 tool_call。
- 不接真实模型时，可以用 mock provider 跑通 workflow 测试。
