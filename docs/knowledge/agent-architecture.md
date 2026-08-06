# 知识文档：Agent 抽象与职责划分

> 对应代码：`backend/app/agents/`（`base.py`、`planner.py`、`writer.py`、`reviewer.py`、`_json.py`）

## 1. 核心设计决策：Agent 保持"纯粹"

`BaseAgent` 只负责三件事：

1. 构造放入 LLM 的 prompt（system prompt + user prompt）。
2. 调用 LLM。
3. 把原始输出解析为结构化 `output`。

**步骤生命周期（创建 RunStep、写 run_events、成本汇总）全部由上层 workflow 统一管理**，Agent 不碰数据库。这样：

- Agent 可以独立单元测试（不依赖数据库）。
- workflow 可以自由编排、复用一个 Agent。
- 职责单一，Agent 失败时容易定位到是 prompt 问题还是解析问题。

## 2. 两个契约类型

```python
@dataclass
class AgentContext:
    run: Run
    task: Task
    input: dict[str, Any]          # 该 run 的输入快照
    previous: dict[str, dict[str, Any]] = ...  # agent_id -> output（跨轮次传递）

@dataclass
class AgentResult:
    agent_id: str
    name: str
    message: str                    # 展示给用户的总结文本
    output: dict[str, Any]          # 结构化输出，workflow 据此消费
    usage: LLMUsage = ...
    latency_ms: int = 0
```

`previous` 是 Agent 之间传递结果的通道，例如 `previous["agent_planner"]`、`previous["agent_writer"]`、`previous["agent_reviewer"]`。

## 3. BaseAgent 骨架

```python
class BaseAgent(ABC):
    agent_id: str        # 如 "agent_planner"
    name: str            # 如 "Planner"
    system_prompt: str

    @abstractmethod
    def build_user_prompt(self, ctx: AgentContext) -> str: ...

    def parse(self, content: str) -> dict[str, Any]:
        return {"content": content}   # 默认原样包裹

    def run(self, ctx: AgentContext) -> AgentResult:
        llm = get_llm_provider()
        messages = [
            LLMMessage(role="system", content=self.system_prompt),
            LLMMessage(role="user", content=self.build_user_prompt(ctx)),
        ]
        result = llm.chat(messages)
        return AgentResult(
            agent_id=self.agent_id,
            name=self.name,
            message=result.content,
            output=self.parse(result.content),
            usage=result.usage,
            latency_ms=result.latency_ms,
        )
```

子类只需实现 `build_user_prompt`，并按需覆写 `parse`。

## 4. 三个 Agent 的 parse 差异

| Agent | `parse` 行为 |
|---|---|
| Planner | 用 `load_json` 解析，归一化 `steps`（补 `sequence`、兜底 `name`/`description`），无合法 steps 抛 `LLMError` |
| Writer | 去掉可能包裹的 ``` 代码块，返回 `{"markdown": text}` |
| Reviewer | 用 `load_json` 解析，校验 `quality` 只能是 `pass`/`revision`，否则抛 `LLMError` |

结构化约定：
- Planner 输出 `{"steps": [{"name", "description"}]}`。
- Reviewer 输出 `{"quality", "score", "feedback", "final_content"}`。

## 5. 容错 JSON 解析器（`_json.py`）

模型常输出带 Markdown 代码块或夹杂多余文字，`load_json` 做了容错：

```python
def load_json(content, *, what="Agent 输出"):
    text = content.strip()
    if text.startswith("```"):            # 剥掉 ```json 包裹
        text = text[text.find("\n") + 1:]
        if text.endswith("```"):
            text = text[:-3].strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")   # 退一步截取最外层 {...}
        if start != -1 and end > start:
            data = json.loads(text[start:end + 1])
        else:
            raise LLMError(f"{what}不是合法 JSON")
    if not isinstance(data, dict):
        raise LLMError(f"{what}不是 JSON 对象")
    return data
```

**注意**：JSON 非法的 Agent 输出会抛 `LLMError`，由 workflow 走异常路径（当前整体标记 run failed）。后续可加"修复重试"策略。

## 6. 测试要点（`test_agents.py`）

- 用 `patch("app.agents.base.get_llm_provider", return_value=MockLLMProvider(latency_ms=0))`，不依赖真实模型与数据库。
- 直接测 `parse` 的容错：非法 JSON 抛 `LLMError`；带 ```json 包裹的能解析成功。
- 用 `_make_context` 构造最小 `AgentContext`（Task + Run + input + previous）。

## 7. 扩展一个新 Agent 的步骤

1. 定义输出 schema 约定（见上面三类的结构化输出）。
2. 继承 `BaseAgent`，写 `system_prompt` 和 `build_user_prompt`，必要时覆写 `parse`。
3. 在 mock 里加对应角色的关键词分支（见 `llm-mock-provider.md`）。
4. 加 `parse` 单元测试。
5. 在 workflow 里编排并传 `previous` 上下文。