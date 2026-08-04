# Multi Agents 安全与权限设计

## 1. 目标

Multi-agent 系统会让 Agent 访问工具、数据和外部服务，因此安全边界必须从第一版就纳入设计。

目标：

- 用户数据隔离。
- Agent 工具权限可控。
- 高风险操作必须审批。
- 所有外部影响可审计。
- 敏感信息不泄露到日志、事件或模型上下文。

## 2. 权限对象

建议核心对象：

```txt
User
Team
Project
Task
Run
Agent
Tool
Connector
Artifact
Permission
Approval
AuditLog
```

MVP 可以先不做完整团队体系，但代码设计上保留 `project_id` 和 `created_by`。

## 3. 角色模型

基础角色：

```txt
owner
admin
developer
operator
viewer
```

权限示例：

```txt
task:create
task:read
run:create
run:cancel
run:retry
run:approve
agent:manage
tool:manage
artifact:read
audit:read
```

## 4. Tool 风险等级

工具风险分三类：

```txt
safe
sensitive
dangerous
```

`safe`：

- 只读公开数据。
- 不产生外部影响。
- 不访问隐私数据。

`sensitive`：

- 访问用户私有数据。
- 读取项目内部资料。
- 可能包含凭证、合同、客户信息。

`dangerous`：

- 写文件。
- 运行代码。
- 发邮件。
- 创建 issue。
- 部署应用。
- 付款或触发业务动作。

## 5. 审批策略

需要审批的情况：

- Tool `requires_approval = true`。
- 风险等级为 `dangerous`。
- 成本超过阈值。
- Agent 请求访问未授权数据。
- 外部写操作。
- 代码执行或命令执行。

审批记录必须保存：

```txt
request payload
risk summary
requested by
approved by
decision
timestamp
```

审批通过后，只能执行审批时展示的原始请求，不能让 Agent 修改参数后复用审批。

## 6. Agent 权限

Agent 权限建议使用白名单。

规则：

- Agent 默认没有工具权限。
- Workflow 可以进一步限制 Agent 权限。
- Project 可以进一步限制可用工具。
- 高风险工具即使授权也需要审批。

权限检查顺序：

```txt
user permission
  -> project permission
  -> workflow permission
  -> agent tool permission
  -> tool risk policy
  -> approval policy
```

## 7. 数据访问控制

需要控制：

- 用户是否能查看 task。
- 用户是否能查看 run。
- 用户是否能查看 artifact。
- Agent 是否能读取项目知识库。
- Tool 是否能访问外部连接器。

规则：

- API 层做用户权限检查。
- Service 层做业务权限检查。
- Tool Runtime 做工具权限检查。
- Context Builder 做上下文权限检查。

## 8. 密钥管理

原则：

- API key 不写入数据库明文。
- 不写入日志。
- 不进入 run_events。
- 不进入 LLM prompt。
- 不返回前端。

建议：

- 本地使用 `.env`。
- 生产使用 secret manager。
- Connector token 加密存储。
- 支持 token 轮换。

## 9. 日志与脱敏

需要脱敏：

- API key。
- OAuth token。
- Authorization header。
- Cookie。
- 私密邮箱、电话号码、身份证件。
- 数据库连接串密码。

日志中可以保存：

- request id。
- run id。
- step id。
- tool name。
- 状态。
- 耗时。
- 错误类型。

不要默认保存完整敏感 payload。

## 10. 沙箱执行

代码执行和命令执行必须沙箱化。

限制：

- CPU。
- 内存。
- 执行时间。
- 文件系统。
- 网络访问。
- 环境变量。

规则：

- 默认禁止网络。
- 默认只允许临时目录。
- 禁止读取宿主机敏感路径。
- 命令执行需要审批。
- 执行结果作为 artifact 保存。

## 11. 外部写操作

外部写操作包括：

- 发送邮件。
- 创建 GitHub issue。
- 修改 Notion 页面。
- 上传文件。
- 部署应用。
- 调用付款接口。

要求：

- 必须审批。
- 必须展示操作摘要。
- 必须记录审计日志。
- 必须支持失败回报。
- 能 dry run 的工具优先 dry run。

## 12. 审计日志

审计日志记录：

- 用户登录。
- 权限变更。
- Tool 启用和禁用。
- Agent 配置修改。
- 高风险工具调用。
- 审批决定。
- 外部写操作。

审计日志要求：

- 追加写入。
- 不允许普通用户修改。
- 保留时间可配置。

## 13. MVP 安全范围

第一版必须实现：

- 基础 tool risk level。
- dangerous tool 审批。
- run cancel 权限检查。
- event payload 脱敏。
- API key 不落库。

第二阶段实现：

- Agent tool 白名单。
- Project 级权限。
- AuditLog。
- Connector token 加密。

第三阶段实现：

- 沙箱执行。
- 企业 RBAC。
- SSO。
- 数据保留策略。
