# V2 迭代计划

> 本文档基于 V1(Step 1–11)实现过程中暴露的架构债务,给出 V2 的迭代方向、主题划分与推进顺序。
> 制定日期:2026-08-11
> 状态:草案

## 一、背景:V1 的真实债务

以下问题在 V1 review 中实际确认,会随规模放大成为瓶颈:

| # | 债务 | 位置 | 影响 |
|---|------|------|------|
| 1 | Worker 阻塞审批 | [runner.py `_wait_for_approval`](../backend/app/tools/runner.py) | `time.sleep` 轮询 300s,单 worker 部署下审批未决时整个队列卡死 |
| 2 | `_append_event` 重复 4 处 + `MAX(sequence)+1` 竞态 | runner / run_service / sequential / run_worker | 多 worker 并发同一 run 时会撞 sequence |
| 3 | 工作流硬编码 | [run_worker.py `SequentialWorkflow()`](../backend/app/workers/run_worker.py) | DB 有 `workflow_name`/`workflow_version` 字段但只有一种实现,无法按 run 选择 |
| 4 | Agent 无自循环 | [base.py `BaseAgent.run`](../backend/app/agents/base.py) | 每个 Agent 只调一次 LLM、最多声明一次工具调用,无 ReAct |
| 5 | 无 token 级流式 | [openai_compat.py `chat`](../backend/app/llms/openai_compat.py) | Agent.run 等完整响应才返回,前端只能看 step 级粒度 |
| 6 | 无跨 run 记忆 | — | 每次 run 从零开始,不能复用历史产物/反馈 |

## 二、V2 主题(按性价比排序)

### 主题 A:工作流引擎化(架构基础)

把 `SequentialWorkflow` 的硬编码拆开,变成可配置的 DAG。

- **工作流注册表**:按 `workflow_name` 从 registry 取 workflow 类,worker 不再直接 import
- **DAG 编排器**:支持并行分支(如 Planner 后并行跑两个 Researcher)、条件路由(Reviewer pass→Artifact, fail→回到 Writer 或直接 fail)
- **可配置重试策略**:per-step 重试,而不是整个 run 级别
- **step 间依赖声明**:替代当前 `previous` dict 的隐式约定

**验收标准**:加一个新工作流 = 加一个文件 + 注册一行,不改编排器。

### 主题 B:异步化 + 流式(用户体验)

解决两个"等"的问题。

- **审批改异步**:用 PG `LISTEN/NOTIFY` 或 RQ `enqueue_at` 延续执行,替代 `time.sleep` 轮询。worker 释放出来处理其他 job,审批回来时重新入队继续
- **token 流式**:`LLMProvider.chat` 加 `stream=True`,通过 SSE 把 Agent 的 token 实时推到前端
- **事件并发安全**:`_append_event` 抽到公共 helper,sequence 用 DB 唯一约束 `(run_id, sequence)` + 重试,而不是 `SELECT MAX + 1`

**验收标准**:审批中的 run 不占用 worker;前端能看到 Writer 逐字输出。

### 主题 C:Agent 能力增强(功能深度)

让 Agent 真正"智能",而不只是一次性 prompt 模板。

- **ReAct 循环**:Agent 内部多轮"思考→工具→观察→再思考",由 Agent 自己决定何时结束
- **Agent 间消息传递**:替代 `previous` dict,改成显式 message bus,Agent 可选择性订阅上游消息
- **Agent 配置化**:system_prompt、model、temperature 从配置/DB 读,不写死在代码里
- **工具动态注册**:支持从 DB 或配置加载工具,不重启服务

**验收标准**:Researcher 能在一次 run 内连续调用多个工具,而非只声明一次。

### 主题 D:可观测性 + 记忆(运维与积累)

跑起来后才知道哪里慢、哪里贵、哪里错。

- **结构化 trace**:每个 Agent 调用记一条 span(run_id → step_id → agent_id → llm_call),前端可看完整调用树(类似 LangSmith trace 视图)
- **真实成本核算**:per-model 单价表,替代当前 `_estimate_cost` 的固定 0.5/2.0
- **跨 run 记忆**:把成功的 Artifact + Reviewer feedback 存成知识库,后续相似任务可检索复用(轻量 RAG)
- **失败归因**:LLM 超时 vs JSON 解析失败 vs 工具失败,分类统计,而非都进 `error_message`

**验收标准**:任意一次 run 能在 UI 看到完整调用树 + 每段耗时 + 真实成本;相似任务能命中历史记忆。

## 三、推进顺序

```
主题 A(工作流引擎)  ← 拆掉硬编码,其他主题才有落点
   ↓
主题 B(异步 + 流式)  ← 解决 worker 卡死 + 用户体验
   ↓
主题 C(ReAct + 配置化)  ← 让 Agent 真正有用
   ↓
主题 D(trace + 记忆)  ← 规模化运维
```

## 四、V2 明确不做的事(避免过度设计)

- **多租户 / RBAC**:当前是单团队工具,加权限会拖慢核心迭代
- **自定义工作流可视化编辑器**:除非工作流引擎稳定后有强需求,否则 YAML/Python 配置足够
- **多 LLM 路由 / 降级**:当前一个 provider 够用,等真有 model fallback 需求再做

## 五、北极星指标

V2 完成后,以下三件事应该从"需要改代码"变成"需要改配置":

1. 加一个新工作流
2. 加一个新 Agent
3. 加一个新工具

当前 `SequentialWorkflow.execute` 把拓扑、取消检查、事件写入、产物生成都耦合在一起——这是 V2 最该拆的地方。
