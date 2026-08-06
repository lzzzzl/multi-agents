# 知识文档：LLM Provider 抽象与 OpenAI 兼容接入

> 本文是**实现记录**，讲"实际怎么做的、踩过什么坑"，与 `technical-architecture.md`（设计稿）互补。
> 对应代码：`backend/app/llms/`、`backend/app/core/config.py`

## 1. 为什么做抽象层

业务层（Agent、Workflow）不应直接依赖某个模型 SDK。抽象层的目的：

- 模型供应商可替换（DeepSeek / 通义 / 智谱 / Ollama / OpenAI）。
- 无 API Key 时能用 mock 兜底，本地开发和中 CI 测试不阻塞。
- 统一拿到 `LLMResult`（content + usage + latency），便于 cost 统计和可观测。

## 2. 核心类型（不绑定 SDK）

`backend/app/llms/types.py` 定义了轻量 dataclass，避免把某个 SDK 的类型泄漏到业务层：

```python
@dataclass
class LLMMessage:
    role: str          # system / user / assistant
    content: str

@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

@dataclass
class LLMResult:
    content: str
    usage: LLMUsage = ...
    latency_ms: int = 0
    raw: dict | None = None

class LLMError(RuntimeError):
    def __init__(self, message, *, status_code=None): ...
```

`LLMProvider` 是一个抽象基类，只声明一个 `chat()` 方法：

```python
class LLMProvider(ABC):
    model: str
    @abstractmethod
    def chat(self, messages: list[LLMMessage], *,
             temperature: float = 0.7, max_tokens: int | None = None) -> LLMResult: ...
```

## 3. 工厂与配置路由

入口是 `get_llm_provider()`（`backend/app/llms/__init__.py`），根据 `settings.LLM_PROVIDER` 分流：

| `LLM_PROVIDER` 值 | 行为 |
|---|---|
| `mock` / `local` / `fake` | 返回 `MockLLMProvider`（离线兜底） |
| `deepseek` / `openai` / `dashscope` / `zhipu` / `ollama` / `openai_compat` | 返回 `OpenAICompatProvider` |
| 其他未知值 | 打 warning 并回退到 mock，避免直接崩溃 |

配置项（`config.py`）：

```txt
LLM_PROVIDER=mock            # 默认 mock，无 key 本地跑通优先
LLM_API_KEY=                 # 主 key
LLM_BASE_URL=https://api.deepseek.com   # 兼容网关地址
LLM_MODEL=deepseek-chat
# 兼容旧配置：OPENAI_API_KEY / DEFAULT_MODEL 作为缺省来源
```

由于同时支持新旧两套变量名，用 property 归一化：

```python
@property
def effective_llm_api_key(self) -> str:
    return self.LLM_API_KEY or self.OPENAI_API_KEY

@property
def effective_llm_model(self) -> str:
    return self.LLM_MODEL or self.DEFAULT_MODEL
```

## 4. OpenAI 兼容 `chat/completions` 调用

`OpenAICompatProvider` 用 `httpx.Client` 同步 POST `{base_url}/chat/completions`：

- 未配置 key 时直接抛 `LLMError`，提示去 `.env` 填 `LLM_API_KEY` 或切 `LLM_PROVIDER=mock`。
- 超时默认 120s。
- 记录 `latency_ms` 用于前端展示和成本统计。

## 5. 踩过的坑（重点）

### 5.1 推理模型输出在 `reasoning_content`，`content` 可能为空

deepseek 推理模型（如 `deepseek-v4-flash`）会把思考过程放在 `reasoning_content`。当 token 预算耗尽时 `content` 会为空。**必须回退**：

```python
content = message.get("content") or message.get("reasoning_content") or ""
if not content:
    raise LLMError("LLM 响应 content 与 reasoning_content 均为空")
```

如果不做这个回退，思考型模型会经常返回空正文，运行表现为"Agent 什么都没输出"。

### 5.2 多层错误处理，逐层给出可定位的报错

```python
with httpx.Client(timeout=self.timeout) as client:
    resp = client.post(f"{self.base_url}/chat/completions",
                       headers=headers, json=payload)
# 网络层
except httpx.HTTPError as exc:
    raise LLMError(f"LLM 请求失败: {exc}") from exc

# HTTP 非 200
if resp.status_code != 200:
    raise LLMError(f"LLM 返回 {resp.status_code}: {detail}", status_code=resp.status_code)

# 响应非 JSON
try: data = resp.json()
except json.JSONDecodeError as exc:
    raise LLMError("LLM 返回非 JSON 响应") from exc

# 缺关键字段
try: message = data["choices"][0]["message"]
except (KeyError, IndexError, TypeError) as exc:
    raise LLMError("LLM 响应缺少 choices/message 字段") from exc
```

### 5.3 token 统计字段映射

OpenAI 兼容网关返回的 usage 用 `prompt_tokens` / `completion_tokens`，要映射到内部 `LLMUsage.input_tokens / output_tokens`：

```python
usage = data.get("usage") or {}
LLMUsage(
    input_tokens=usage.get("prompt_tokens", 0),
    output_tokens=usage.get("completion_tokens", 0),
    model=self.model,
)
```

## 6. 如何接入一个新的 OpenAI 兼容供应商

1. 确认它有 `/chat/completions` 接口（OpenAI 协议）。
2. 在 `.env` 填 `LLM_BASE_URL`（网关根地址，不带 `/v1/chat/completions`）和 `LLM_API_KEY`。
3. 把 `LLM_PROVIDER` 设为该供应商名，或复用 `openai_compat`。
4. 若输出走 `reasoning_content`，确认 5.1 的回退逻辑已生效。

## 7. 验证

运行端到端验证（真实模型）：

```bash
cd backend
uv run pytest tests/test_agents.py tests/test_workflow.py   # 走 mock
# 切真实模型后，创建任务并观察 run 事件与 artifact 是否生成
```

## 8. 后续可改进

- 支持 `stream=True` 流式输出（当前是阻塞式单次请求）。
- 增加 `max_tokens` 显式传参（当前主要靠 `default`）。
- 把 usage 持久化到独立的 `llm_calls` 表（当前只在 `run_steps.metadata_` 里记录 token/model/latency）。