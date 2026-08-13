# V2 迭代计划

> 本文档基于 V1 实现过程中暴露的架构债务,给出 V2 的迭代方向、主题划分与推进顺序。
> 制定日期:2026-08-11
> 修订日期:2026-08-13
> 状态:草案

## 一、背景:V1 的真实债务

以下问题在 V1 review 中实际确认(部分已在迭代中部分收敛),会随规模放大成为瓶颈:


| #   | 债务                                                    | 位置                                                                                                             | 影响                                                           |
| --- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| 1   | Worker 阻塞审批                                           | [runner.py](../backend/app/tools/runner.py) `_wait_for_approval`                                               | `time.sleep` 轮询 300s,单 worker 部署下审批未决时整个队列卡死                 |
| 2   | 事件 `sequence` 并发竞态(核心逻辑已收敛到 `eventing.py`,仍残留 4 处薄封装) | [eventing.py](../backend/app/services/eventing.py) `append_event`                                              | 多 worker 并发同一 run 时 `SELECT MAX(sequence)+1` 会撞 sequence     |
| 3   | 工作流硬编码                                                | [run_worker.py](../backend/app/workers/run_worker.py) `SequentialWorkflow()`                                   | DB 有 `workflow_name`/`workflow_version` 字段但只有一种实现,无法按 run 选择 |
| 4   | Agent 无自循环                                            | [base.py](../backend/app/agents/base.py) `BaseAgent.run`                                                       | 每个 Agent 只调一次 LLM、最多声明一次工具调用,无 ReAct                         |
| 5   | 无 token 级流式                                           | [openai_compat.py](../backend/app/llms/openai_compat.py) `chat`                                                | Agent.run 等完整响应才返回,前端只能看 step 级粒度                            |
| 6   | 无跨 run 记忆                                             | —                                                                                                              | 每次 run 从零开始,不能复用历史产物/反馈                                      |
| 7   | 成本/步数预算形同虚设                                           | [config.py](../backend/app/core/config.py) `RUN_MAX_STEPS`[/](../backend/app/core/config.py)`RUN_MAX_COST_USD` | 配置已定义但从未被执行,超步数/超成本不会熔断                                      |
| 8   | 取消只在 step 边界生效                                        | [sequential.py](../backend/app/workflows/sequential.py) `_check_cancelled`                                     | LLM/工具执行期间无法打断(审批轮询除外)                                       |
| 9   | 事件推送靠 DB 轮询                                           | [event_service.py](../backend/app/services/event_service.py) `stream`                                          | 每 0.5s 查库,延迟与数据库负载随订阅数上升                                     |




## 二、V2 主题(按依赖与性价比排序)



### 主题 A:工作流引擎化 + 挂起/恢复(架构基础)

把 `SequentialWorkflow` 的硬编码拆开,变成可配置的 DAG,并提供「暂停—恢复」原语,作为审批、取消、重试的共同底座。

- **工作流注册表**:按 `workflow_name` 从 registry 取 workflow 类,worker 不再直接 import
- **DAG 编排器**:支持并行分支(如 Planner 后并行跑两个 Researcher)、条件路由(Reviewer pass→Artifact, fail→回到 Writer 或直接 fail)
- **step 间依赖声明**:替代当前 `previous` dict 的隐式约定
- **挂起/恢复(checkpoint/resume)**:执行到任意 step 边界可暂停并持久化进度、释放 worker,等外部事件(审批/人工输入)后恢复续跑,恢复后不重复执行已完成 step
- **可配置重试策略**:per-step 重试,而非整个 run 级别;重试需配合幂等设计(见「横切关注点」)

**验收标准**:

- 加一个新工作流 = 加一个文件 + 注册一行,不改编排器。
- 工作流能在任意 step 边界暂停并恢复,恢复后正确续跑、不重复执行已完成 step。



### 主题 B:异步化 + 流式(用户体验)

基于 A 的挂起/恢复能力,解决两个「等」的问题。

- **审批改异步**:用 PG `LISTEN/NOTIFY` 或 RQ `enqueue_at` 延续执行,替代 `time.sleep` 轮询。审批期间释放 worker 处理其他 job,审批回来时重新入队继续
- **token 流式**:`LLMProvider.chat` 加 `stream=True`,通过 SSE 把 Agent 的 token 实时推到前端
- **事件并发安全**:sequence 改为由数据库保证(唯一约束 `(run_id, sequence)` + `ON CONFLICT` 重试,或 per-run 序列),而非 `SELECT MAX(sequence)+1`
- **事件推送 pub/sub 化**:SSE 从 DB 轮询升级为 Redis pub/sub,降低延迟与数据库负载

**验收标准**:

- 审批中的 run 不占用 worker;审批恢复后能正确续跑、不重复执行已完成 step。
- 前端能看到 Writer 逐字输出;断线重连不丢 token/事件。



### 主题 C:Agent 能力增强(功能深度)

让 Agent 真正「智能」,而不只是一次性 prompt 模板。

- **ReAct 循环**:Agent 内部多轮「思考→工具→观察→再思考」,由 Agent 自己决定何时结束(含轮次上限)
- **Agent 间消息传递**:替代 `previous` dict,改成显式 message bus,Agent 可选择性订阅上游消息
- **Agent 配置化**:system_prompt、model、temperature 从配置/DB 读,不写死在代码里(行为逻辑边界见「北极星指标」)
- **工具动态注册**:支持从 DB 或配置加载工具,不重启服务

**验收标准**:Researcher 能在一次 run 内连续调用多个工具,而非只声明一次。

### 主题 D:可观测性 + 记忆 + 成本治理(运维与积累)

跑起来后才知道哪里慢、哪里贵、哪里错。

- **结构化 trace**:每个 Agent 调用记一条 span(run_id → step_id → agent_id → llm_call),前端可看完整调用树(类似 LangSmith trace 视图)
- **失败归因**:LLM 超时 vs JSON 解析失败 vs 工具失败,分类统计,而非都进 `error_message`
- **真实成本核算**:per-model 单价表,替代当前 `_estimate_cost` 的固定 0.5/2.0;并统一币种单位
- **预算执行/熔断**:真正执行 `RUN_MAX_STEPS`/`RUN_MAX_COST_USD`,超限即熔断并记录原因
- **跨 run 记忆**:把成功的 Artifact + Reviewer feedback 存成知识库,后续相似任务可检索复用(轻量 RAG)

**验收标准**:任意一次 run 能在 UI 看到完整调用树 + 每段耗时 + 真实成本;超步数/超成本能自动熔断;相似任务能命中历史记忆。

> 注:trace 与失败归因的**轻量 MVP** 建议紧跟主题 A/B 尽早落地,为 DAG/异步/ReAct 提供调试底座;完整 trace UI、真实成本核算与 RAG 记忆可放到最后。



## 三、横切关注点(贯穿所有主题)

以下不是独立主题,但每个主题落地时都必须同步考虑:

- **测试策略**:为 V2 引入的并发、异步、流式、ReAct 补足测试护栏。至少覆盖:sequence 并发竞态、审批挂起/恢复的集成测试、DAG 拓扑契约测试、流式断线重连测试、ReAct 轮次上限测试。当前前端仅 1 个组件测试,需同步补齐。
- **数据模型演进**:DAG 依赖、workflow 定义、span、跨 run 记忆都需要新表/字段,随主题一并规划迁移。当前 `workflow_name`/`workflow_version` 字段已存在但未被消费,需由引擎实现补齐。
- **幂等性/副作用安全**:per-step 重试与挂起恢复都可能让某个 step/工具被执行多次,尤其 `send_notification` 这类有外部副作用的工具。需明确工具调用幂等语义,避免重复副作用。
- **取消即时性**:让 cancel 能及时打断正在进行的 LLM 调用与工具执行,而不只是在 step 边界检查;与主题 B 的异步化协同设计。
- **成本单位统一**:`_estimate_cost` 注释为「元」,而 `RUN_MAX_COST_USD` 为美元,需统一为单一币种并明确单位。



## 四、推进顺序

```
主题 A(工作流引擎 + 挂起/恢复)          ← 拆掉硬编码,提供 checkpoint/resume 原语
   ↓
主题 B(异步 + 流式) + 可观测性 MVP       ← 审批/取消/流式落地,同时补 trace/失败归因调试底座
   ↓
主题 C(ReAct + 配置化)                   ← 让 Agent 真正有用
   ↓
主题 D(完整 trace UI + 真实成本 + 记忆)   ← 规模化运维与积累
```

横切关注点(测试、数据模型、幂等、取消、单位)随各主题并行推进,不单列阶段。

## 五、V2 明确不做的事(避免过度设计)

- **多租户 / RBAC**:当前是单团队工具,加权限会拖慢核心迭代
- **自定义工作流可视化编辑器**:除非工作流引擎稳定后有强需求,否则 YAML/Python 配置足够
- **多 LLM 路由 / 降级**:当前一个 provider 够用,等真有 model fallback 需求再做
- **分布式调度 / 多 worker 强一致事务**:继续用 RQ + 单队列,不引入 Celery / Temporal 等重框架



## 六、北极星指标

V2 完成后,以下三件事应该从「需要改代码」变成「需要改配置」:

1. 加一个新工作流
2. 加一个新 Agent
3. 加一个新工具

其中「加一个新 Agent」需要明确边界:Agent 的**行为逻辑**(`build_user_prompt`、`parse`)通常仍需少量代码,除非采用「通用 Agent 模板 + prompt schema + 工具集 + 解析 schema」的全配置化设计。因此该目标应理解为「加一个新 Agent = 声明式配置 + 少量解析代码」,而非完全零代码。

当前 `SequentialWorkflow.execute` 把拓扑、取消检查、事件写入、产物生成都耦合在一起——这是 V2 最该拆的地方。