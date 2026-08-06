# 知识文档：Mock LLM 的离线开发与测试策略

> 对应代码：`backend/app/llms/mock.py`
> 配套测试：`backend/tests/test_agents.py`、`backend/tests/test_workflow.py`

## 1. 为什么需要 Mock LLM

- **无 API Key 也能本地把流程端到端跑通**（开发不阻塞）。
- **自动化测试不依赖真实模型**（稳定、免费、快），这是测试策略的核心要求。
- 通过 `get_llm_provider()` 路由，当 `LLM_PROVIDER` 为 `mock` / `local` / `fake` 时启用。

## 2. 核心思路：按 system prompt 识别角色

真实场景下，模型是"无状态"的，我们不能靠调用顺序判断这次是 Planner / Writer / Reviewer。Mock 采用**内容识别**：

- 识别角色的依据是 **system prompt 里的关键词**（不是 user 文本）。
- 提取任务标题的依据是 **user 文本里的 `任务标题:` 一行**。

```python
system_text = " ".join(m.content for m in messages if m.role == "system")
user_text = " ".join(m.content for m in messages if m.role == "user")

if "质量评审 Agent" in system_text or "reviewer" in system_text.lower():
    # Reviewer 分支
elif "报告撰写 Agent" in system_text or "writer" in system_text.lower():
    # Writer 分支
else:
    # 其余默认当 Planner
```

这样只要 Agent 的 system prompt 保持稳定，mock 就能稳定返回对应角色的输出。

## 3. 各角色返回什么

- **Reviewer**：结构化 JSON `{"quality", "score", "feedback", "final_content"}`。
- **Writer**：纯 Markdown 正文（以 `# ` 标题开头）。
- **Planner**（默认）：结构化 JSON `{"steps": [...]}`。

## 4. 关键技巧：让 Mock 能"触发一次重写循环"

Workflow 的 Writer→Reviewer 重写循环需要一个"首次不通过、重写后通过"的确定性行为，否则测试无法验证循环逻辑。Mock 的做法是**用 user 文本里的修订标记做状态机**：

- **首个 Reviewer**：user 文本里没有"已按评审意见修订" → 返回 `quality: "revision"`（打回一次）。
- **重写后的 Writer**：user 文本含"评审意见" → 输出带"已按评审意见修订"标记的稿子。
- **重写后的 Reviewer**：user 文本含"已按评审意见修订" → 这次返回 `quality: "pass"`。

```python
# Reviewer
if "已按评审意见修订" in user_text:
    return '{"quality": "pass", ...}'
return '{"quality": "revision", ...}'

# Writer
if "评审意见" in user_text:
    return "# {title}\n\n## 正文\n\n已按评审意见修订...\n"
```

于是 `test_workflow.py` 里预期 `steps == 5`（Planner + 首次 Writer/Reviewer + 重写 Writer/Reviewer）、`rewrites == 1`，是确定性的。

## 5. 用量与延迟

Mock 返回伪造的 usege 和延迟，便于验证 cost 汇总逻辑：

```python
time.sleep(self.latency_ms / 1000)          # 可配置，测试里设 0 以加速
return LLMResult(
    content=content,
    usage=LLMUsage(input_tokens=120, output_tokens=len(content) // 4, model=self.model),
    latency_ms=self.latency_ms,
)
```

## 6. 在测试里如何接入

单元测试用 `patch` 把 `get_llm_provider` 替换成 `MockLLMProvider`，不依赖数据库：

```python
from unittest.mock import patch
from app.agents import PlannerAgent

@patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))
def test_planner_produces_steps(_mock):
    result = PlannerAgent().run(_make_context())
    assert isinstance(result.output["steps"], list) and len(result.output["steps"]) >= 1
```

**注意 patch 的位置**：要 patch 的是 `get_llm_provider` 被**引用**的地方，即 `app.agents.base.get_llm_provider`（Agent.run 里调用），而不是 `app.llms` 里的定义处。

## 7. 局限与改进方向

- **硬编码了角色关键词**：system prompt 一旦改词，mock 分支会失效。建议把角色标识抽成显式字段而不是靠字符串匹配。
- **只覆盖"成功路径"**：目前 mock 不模拟 timeout / rate limit / 非法 JSON。要测错误处理，可扩展 mock 支持按配置返回非法 JSON 或抛 `LLMError`。
- **输出与真实模型不同**：mock 的 JSON 永远是合法且难度固定的，不能替代真实模型做质量评估，只能用于流程回归。