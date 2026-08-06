# Multi Agents 后续迭代路线

## 1. 路线目标

本路线图用于指导项目从空仓库逐步演进为可用的 multi-agent 工作台。每个阶段都需要有明确交付物、验收标准和暂不处理的范围，避免一开始陷入过大的 Agent 自动化想象。

总体方向：

- Phase 1：搭出可运行的基础工作台。
- Phase 2：实现可观察的 Agent Runtime。
- Phase 3：完善 Tool 系统和人工审批。
- Phase 4：支持多 Agent 并行协作。
- Phase 5：加入记忆、检索、评估和生产化能力。
- Phase 6：建设 Workflow Studio 和可视化编排。
- Phase 7：引入插件、连接器和工具市场。
- Phase 8：支持代码执行沙箱和复杂自动化。
- Phase 9：建设评估、自优化和成本治理体系。
- Phase 10：扩展企业级协作、多租户和部署能力。

## 2. Phase 1: 基础工作台

目标：建立前后端基础工程、核心数据表和任务运行链路。

交付内容：

- 初始化 monorepo 目录结构。
- 搭建 FastAPI 后端服务。
- 搭建 Next.js 前端应用。
- 配置 PostgreSQL、Redis。
- 建立基础数据库迁移。
- 实现 `Task`、`Run`、`RunEvent`、`Artifact` 数据模型。
- 实现创建任务、创建运行、查询运行详情 API。
- 实现后台 worker 接收并执行一个模拟任务。
- 实现 SSE 事件流。
- 实现前端任务创建页、任务列表页、运行详情页。

验收标准：

- 用户可以在前端创建一个任务。
- 后端可以生成对应 `task` 和 `run`。
- Worker 可以模拟执行任务并写入事件。
- 前端可以实时看到运行事件。
- 运行完成后可以看到最终结果。

暂不处理：

- 真实 LLM 调用。
- 复杂 Agent 规划。
- Tool 权限系统。
- 多 Agent 并行。
- 用户体系和团队权限。

## 3. Phase 2: Agent Runtime

目标：实现第一个真正可运行的 Agent workflow。

交付内容：

- 实现 LLM Provider 抽象。
- 接入至少一个模型供应商。
- 实现 `PlannerAgent`、`WriterAgent`。
- 实现固定顺序 workflow。
- 支持结构化 Agent 输出。
- 记录 LLM 调用输入、输出、token、耗时和错误。
- 在前端展示 Agent 消息、步骤状态和最终 Markdown artifact。

推荐 workflow：

```txt
Planner -> Writer -> Reviewer
```

验收标准：

- 用户提交目标后，Planner 能输出结构化计划。
- Writer 能根据计划生成 Markdown 结果。
- Reviewer 能给出质量检查结果。
- 每次 Agent 调用都有事件记录。
- 每次 LLM 调用都能在运行详情页查看摘要信息。

暂不处理：

- 高风险工具调用。
- 长期记忆。
- 多模型路由。
- 自动修复所有失败。

## 4. Phase 3: Tool 系统与审批

目标：建立 Agent 调用外部能力的安全边界。

交付内容：

- 实现 `Tool` 和 `ToolCall` 数据模型。
- 定义 Tool 输入输出 schema。
- 实现 Tool Registry。
- 实现工具风险等级：`safe`、`sensitive`、`dangerous`。
- 实现 `requires_approval` 审批流程。
- 实现工具调用事件。
- 实现至少两个低风险工具。
- 前端展示 Tool Call 参数、结果、耗时和错误。

推荐第一批工具：

- `generate_report`
- `read_document`
- `query_vector_store`
- `web_search`，如果后端具备联网能力

验收标准：

- Agent 可以调用已注册工具。
- Tool 参数会被 schema 校验。
- Tool 执行结果会被记录。
- 高风险工具会暂停运行并等待用户审批。
- 用户审批后运行可以继续。

暂不处理：

- 任意代码执行。
- 自动发邮件、付款、部署等外部写操作。
- 第三方插件市场。

## 5. Phase 4: 多 Agent 并行协作

目标：从单链路 workflow 进化到 Supervisor + Workers 模式。

交付内容：

- 实现 `SupervisorAgent`。
- 实现多个 Worker Agent 并行执行。
- 实现 Synthesizer 汇总输出。
- 支持 step 依赖关系。
- 支持部分失败重试。
- 前端展示 workflow 图和并行步骤状态。
- 支持取消整个 run。

推荐 workflow：

```txt
Supervisor
  -> Researcher A
  -> Researcher B
  -> Researcher C
  -> Synthesizer
  -> Reviewer
```

验收标准：

- Supervisor 可以把任务拆成多个子任务。
- 多个 Worker 可以并行执行。
- 每个 Worker 的事件流独立可查看。
- Synthesizer 可以汇总多个 Worker 输出。
- 单个 Worker 失败时可以重试或降级。

暂不处理：

- 完全自由的 Agent 群聊。
- 无限制自我复制任务。
- 跨项目自动访问数据。

## 6. Phase 5: 记忆、检索、评估与生产化

目标：提升系统可靠性、可维护性和长期使用价值。

交付内容：

- 引入 pgvector 或独立向量数据库。
- 实现项目知识库。
- 支持历史运行结果检索。
- 实现 Agent 结果质量评估。
- 统计运行耗时、token、费用和成功率。
- 接入 OpenTelemetry、Sentry。
- 完善用户、项目、团队权限。
- 支持审计日志。
- 完善测试体系和 CI。

验收标准：

- Agent 可以检索项目知识库。
- 用户可以查看运行成本和质量指标。
- 系统错误可以被监控和追踪。
- 权限边界清晰。
- 常见 workflow 有自动化测试覆盖。

## 7. Phase 6: Workflow Studio 与可视化编排

目标：让用户可以通过可视化方式创建、调试和复用 Agent workflow。

交付内容：

- 引入 workflow graph 数据模型。
- 支持节点、边、条件分支、重试策略和人工审批节点。
- 前端提供 Workflow Studio。
- 支持从运行记录反向查看实际执行路径。
- 支持 workflow 模板保存和复用。
- 支持 dry run 和模拟输入。

高级能力：

- 节点级模型配置。
- 节点级 Tool 权限。
- 子 workflow 复用。
- 条件分支表达式。
- Workflow 版本管理和回滚。

验收标准：

- 用户可以可视化创建一个 Planner -> Worker -> Reviewer workflow。
- 用户可以保存并运行 workflow。
- 运行详情页能展示实际执行路径和节点状态。
- Workflow 修改后不会破坏历史 run 回放。

## 8. Phase 7: 插件、连接器与工具市场

目标：让系统可以扩展外部工具，并支持按项目或团队授权。

交付内容：

- 建立 Connector 抽象。
- 建立插件 manifest 规范。
- 支持工具安装、启用、禁用和权限配置。
- 支持 OAuth 或 API key 类型连接。
- 支持工具调用审计。
- 前端提供 Tool Marketplace 和连接器设置页。

高级能力：

- Gmail、Slack、GitHub、Notion、Google Drive 等连接器。
- 项目级工具白名单。
- Agent 级工具授权。
- 高风险工具审批策略模板。
- 插件版本管理。
- 私有插件导入。

验收标准：

- 用户可以启用一个外部连接器。
- Agent 只能调用已授权工具。
- 每次外部写操作都有审批和审计记录。
- 插件升级不会破坏已有 workflow。

## 9. Phase 8: 沙箱执行与复杂自动化

目标：支持更强的 Agent 执行能力，同时控制安全风险。

交付内容：

- 引入代码执行沙箱。
- 支持临时文件系统和资源限制。
- 支持网络访问策略。
- 支持命令执行审批。
- 支持 browser automation 或 API automation。
- 支持运行产物自动归档。

高级能力：

- Python 代码执行。
- Node.js 脚本执行。
- Playwright 浏览器自动化。
- 数据处理任务。
- 自动生成并运行测试。
- 自动创建 Pull Request。

验收标准：

- 代码执行在隔离环境中运行。
- 沙箱有 CPU、内存、时间和网络限制。
- 高风险命令会触发审批。
- 执行产物可以保存为 artifact。

## 10. Phase 9: 评估、自优化与成本治理

目标：让系统知道 Agent 运行质量如何，并能持续改进。

交付内容：

- 建立 evaluation 数据模型。
- 支持人工评分。
- 支持自动评分。
- 支持 golden dataset。
- 支持 prompt 版本对比。
- 支持模型成本统计。
- 支持运行成功率、失败率和重试率统计。

高级能力：

- Prompt A/B 测试。
- 不同模型对同一 workflow 的质量对比。
- Agent 输出事实性检查。
- Tool 调用准确率评估。
- 自动发现高成本步骤。
- 自动推荐更便宜或更快的模型。

验收标准：

- 每个 workflow 都可以绑定评估集。
- 系统可以对 run 生成质量评分。
- 用户可以看到成本、耗时、成功率趋势。
- Prompt 修改前后可以对比质量变化。

## 11. Phase 10: 企业级协作、多租户与部署

目标：让系统具备团队协作、权限隔离和生产部署能力。

交付内容：

- 引入 Team、Project、Role、Permission。
- 支持项目级数据隔离。
- 支持成员邀请和角色管理。
- 支持审计日志。
- 支持环境分离：dev、staging、production。
- 支持水平扩展 worker。
- 支持备份、迁移和灾难恢复。

高级能力：

- SSO。
- SCIM。
- 细粒度 RBAC。
- 数据保留策略。
- 私有模型网关。
- 企业知识库权限继承。
- 多区域部署。

验收标准：

- 不同项目之间数据隔离。
- 用户只能访问授权 task、run、artifact。
- 管理员可以查看审计日志。
- Worker 可以横向扩展。
- 生产环境有监控、告警和备份。

## 12. 长期探索方向

这些方向可以进入技术预研，但不建议在 MVP 阶段承诺交付。

- Agent 自动生成 workflow。
- Agent 自动生成和测试 Tool。
- 跨项目经验迁移。
- 多模态 Agent，支持图片、音频、视频理解和生成。
- 语音驱动的任务创建和审批。
- Agent 之间的长期协作记忆。
- 组织级知识图谱。
- 自主运维 Agent。
- 多 Agent 仿真和策略博弈。
- 用户偏好学习和个性化工作台。

## 13. 优先级建议

优先做：

- Task / Run / Event 运行链路。
- SSE 实时事件。
- 固定顺序 workflow。
- 结构化 Agent 输出。
- Tool schema 和调用记录。
- 运行历史和调试界面。

暂缓做：

- 复杂长期记忆。
- 复杂多租户。
- 插件市场。
- Agent 自动生成 Agent。
- 高风险外部写操作自动执行。

高级能力优先级：

- 先做 Workflow Studio，再做插件市场。
- 先做工具权限，再做复杂自动化。
- 先做评估数据模型，再做自优化。
- 先做项目级权限，再做企业级 SSO。
- 先做单环境稳定部署，再做多区域部署。

## 14. 里程碑

建议以两周为一个小迭代：

- Milestone 1：项目脚手架和基础 API。
- Milestone 2：任务运行链路和 SSE。
- Milestone 3：第一个 Agent workflow。
- Milestone 4：前端运行详情页。
- Milestone 5：Tool 系统。
- Milestone 6：Supervisor 并行 workflow。
- Milestone 7：RAG 和项目知识库。
- Milestone 8：生产化监控、权限和测试。
- Milestone 9：Workflow Studio。
- Milestone 10：连接器和插件系统。
- Milestone 11：沙箱执行和复杂自动化。
- Milestone 12：评估、自优化和成本治理。
- Milestone 13：企业协作、多租户和生产部署。
