# Multi Agents 数据模型设计

## 1. 设计目标

数据模型需要服务三个核心需求：

- 支撑任务执行和多 Agent 编排。
- 完整记录运行过程，方便调试、回放和审计。
- 为后续 Tool 权限、Artifact 管理、RAG 和评估留出扩展空间。

第一阶段重点表：

```txt
tasks
runs
run_steps
run_events
messages
agents
tools
tool_calls
artifacts
```

## 2. 通用字段

大多数表建议包含：

```txt
id
created_at
updated_at
deleted_at 可选
metadata JSONB 可选
```

ID 可以使用 UUID，也可以使用带前缀的字符串 ID，例如：

```txt
task_...
run_...
step_...
evt_...
agent_...
tool_...
artifact_...
```

## 3. tasks

表示用户提交的任务目标。

字段建议：

```txt
id
project_id 可选
created_by 可选
title
description
status
priority
input JSONB
metadata JSONB
created_at
updated_at
```

状态建议：

```txt
draft
queued
running
completed
failed
cancelled
archived
```

说明：

- `title` 用于列表展示。
- `description` 保存用户自然语言目标。
- `input` 保存结构化输入，例如目标、约束、输出格式。
- `status` 可以由最新 run 状态同步，也可以独立维护。

## 4. runs

表示一次任务执行。一个 task 可以有多次 run，例如重试、不同模型配置、不同 workflow。

字段建议：

```txt
id
task_id
workflow_name
workflow_version
status
started_at
completed_at
failed_at
cancelled_at
error_message
input_snapshot JSONB
output_summary JSONB
cost_summary JSONB
metadata JSONB
created_at
updated_at
```

状态建议：

```txt
queued
running
waiting_for_approval
completed
failed
cancelled
```

说明：

- `input_snapshot` 保存运行开始时的任务输入，避免任务后续修改影响历史回放。
- `output_summary` 保存最终结果摘要。
- `cost_summary` 保存 token、耗时、费用估算。
- `workflow_version` 用于后续 workflow 升级后的兼容和审计。

## 5. run_steps

表示一次 run 中的执行步骤。

字段建议：

```txt
id
run_id
parent_step_id 可选
agent_id 可选
name
type
status
sequence
depends_on JSONB
started_at
completed_at
failed_at
error_message
input JSONB
output JSONB
metadata JSONB
created_at
updated_at
```

类型建议：

```txt
agent
tool
workflow
approval
system
```

状态建议：

```txt
pending
running
waiting_for_approval
completed
failed
skipped
cancelled
```

说明：

- `parent_step_id` 支持子步骤和嵌套 workflow。
- `depends_on` 可以保存依赖 step ID 列表。
- `sequence` 用于顺序展示。

## 6. run_events

表示运行过程的事件流，是可观察性、实时推送和历史回放的核心。

字段建议：

```txt
id
run_id
step_id 可选
agent_id 可选
tool_call_id 可选
type
sequence
payload JSONB
created_at
```

事件类型建议：

```txt
run_started
run_completed
run_failed
run_cancelled

step_started
step_completed
step_failed
step_retried

agent_started
agent_message
agent_completed
agent_failed

llm_call_started
llm_call_completed
llm_call_failed

tool_call_started
tool_call_completed
tool_call_failed

human_approval_required
human_approval_granted
human_approval_rejected

artifact_created
```

索引建议：

```txt
run_events(run_id, sequence)
run_events(run_id, created_at)
run_events(type)
```

说明：

- `sequence` 必须在单个 run 内单调递增。
- SSE 可以用 `sequence` 作为游标。
- `payload` 保存事件的具体内容，不同事件类型可以有不同结构。

## 7. messages

表示用户、系统、Agent 之间的消息。它和 `run_events` 不完全等价，message 更偏语义上下文，event 更偏运行日志。

字段建议：

```txt
id
run_id
step_id 可选
agent_id 可选
role
content
content_type
sequence
metadata JSONB
created_at
```

角色建议：

```txt
user
system
assistant
agent
tool
developer
```

内容类型：

```txt
text
markdown
json
html
file_ref
```

说明：

- LLM 上下文可从 messages 构建。
- 前端聊天式视图可以从 messages 构建。
- 调试 timeline 更适合从 run_events 构建。

## 8. agents

表示 Agent 配置。

字段建议：

```txt
id
name
display_name
role
description
system_prompt
model_provider
model_name
model_config JSONB
input_schema JSONB
output_schema JSONB
memory_policy JSONB
status
metadata JSONB
created_at
updated_at
```

状态建议：

```txt
active
disabled
archived
```

说明：

- `input_schema` 和 `output_schema` 用于结构化执行。
- `memory_policy` 定义使用哪些历史上下文。
- Tool 权限建议通过独立关联表表达。

可选关联表：

```txt
agent_tools
  agent_id
  tool_id
  permission_scope
  created_at
```

## 9. tools

表示 Tool 定义。

字段建议：

```txt
id
name
display_name
description
risk_level
input_schema JSONB
output_schema JSONB
timeout_seconds
requires_approval
status
metadata JSONB
created_at
updated_at
```

风险等级：

```txt
safe
sensitive
dangerous
```

状态建议：

```txt
active
disabled
archived
```

说明：

- Tool 的实际 executor 不一定存数据库，可以通过代码 registry 映射。
- 数据库保存的是工具契约和权限配置。

## 10. tool_calls

表示一次具体工具调用。

字段建议：

```txt
id
run_id
step_id
agent_id 可选
tool_id
status
input JSONB
output JSONB
error_message
started_at
completed_at
duration_ms
approval_id 可选
metadata JSONB
created_at
updated_at
```

状态建议：

```txt
pending
waiting_for_approval
running
completed
failed
cancelled
rejected
```

说明：

- `input` 需要保存调用参数。
- `output` 保存工具执行结果摘要或完整结果。
- 敏感字段需要脱敏后再写入数据库。

## 11. artifacts

表示运行生成的结果文件或结构化结果。

字段建议：

```txt
id
run_id
step_id 可选
created_by_agent_id 可选
type
name
mime_type
content
storage_url
size_bytes
checksum
metadata JSONB
created_at
updated_at
```

类型建议：

```txt
markdown
json
text
html
image
file
report
```

说明：

- 小型 Markdown 或 JSON 可以直接存 `content`。
- 大文件建议存对象存储，数据库只保存 `storage_url`。
- `checksum` 用于校验文件内容。

## 12. approvals

用于人工审批高风险工具调用或关键 workflow 分支。

字段建议：

```txt
id
run_id
step_id 可选
tool_call_id 可选
requested_by_agent_id 可选
status
reason
request_payload JSONB
response_payload JSONB
approved_by 可选
requested_at
resolved_at
created_at
updated_at
```

状态建议：

```txt
pending
approved
rejected
expired
cancelled
```

说明：

- Run 进入审批等待时，状态应变为 `waiting_for_approval`。
- 审批通过后，Worker 可以继续执行。
- 审批拒绝后，Workflow 应明确失败、跳过或走替代分支。

## 13. llm_calls

用于记录模型调用，便于成本统计、调试和评估。

字段建议：

```txt
id
run_id
step_id 可选
agent_id 可选
provider
model
status
prompt_summary
request JSONB
response JSONB
input_tokens
output_tokens
total_tokens
estimated_cost
started_at
completed_at
duration_ms
error_message
metadata JSONB
created_at
updated_at
```

说明：

- 生产环境中不要无条件保存完整 prompt 和 response，需要支持脱敏与配置化。
- `prompt_summary` 用于列表展示。
- `request` 和 `response` 可以按环境决定是否完整保存。

## 14. 关系图

```txt
tasks 1 -> n runs
runs 1 -> n run_steps
runs 1 -> n run_events
runs 1 -> n messages
runs 1 -> n tool_calls
runs 1 -> n artifacts
runs 1 -> n llm_calls

agents 1 -> n run_steps
agents 1 -> n messages
agents 1 -> n tool_calls

tools 1 -> n tool_calls
tool_calls 0/1 -> 1 approvals
```

## 15. 状态同步规则

建议规则：

- `runs.status` 是运行总状态。
- `run_steps.status` 是步骤状态。
- `tasks.status` 可以从最新 run 推导，也可以独立维护。
- 所有关键状态变化都必须写入 `run_events`。
- 前端实时视图优先从事件流更新，页面刷新后从 run、steps、events 重建。

## 16. MVP 数据模型

第一版必须实现：

```txt
tasks
runs
run_steps
run_events
artifacts
```

第二阶段实现：

```txt
agents
messages
llm_calls
```

第三阶段实现：

```txt
tools
tool_calls
approvals
agent_tools
```

后续扩展：

```txt
projects
teams
users
knowledge_documents
vector_chunks
evaluations
audit_logs
```
