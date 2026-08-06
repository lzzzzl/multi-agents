# 知识文档：前端 SSE 实时事件流

> 对应代码：`frontend/lib/api.ts`、`frontend/lib/useRunEvents.ts`、`frontend/components/RunTimeline.tsx`

## 1. 实时方案：REST 拉历史 + SSE 增量

后端事件全部落库（`run_events`），前端采取"**先 REST 拉历史，再 SSE 增量**"的混合方案，而不是纯 SSE。这样页面刷新后能从历史事件完整恢复状态。

## 2. API 客户端（`api.ts`）

- 基地址 `API_BASE`，默认 `http://localhost:8000`，可用 `NEXT_PUBLIC_API_BASE` 覆盖。
- 统一 `request<T>` 包装：解析 `{data, error}`，非 2xx 或 `body.error` 时抛 `ApiClientError`（带 `code`/`message`/`details`）。
- 事件列表接口支持 `after_sequence` 增量拉取：

```typescript
listEvents: (runId, afterSequence?) => request(`/api/runs/${runId}/events${q}`)
```

- SSE 地址构造：

```typescript
export function sseUrl(runId, afterSequence?) {
  const q = afterSequence ? `?after_sequence=${afterSequence}` : "";
  return `${API_BASE}/api/runs/${runId}/events/stream${q}`;
}
```

## 3. `useRunEvents`：三个阶段的 hook

```typescript
const TERMINAL = ["completed", "failed", "cancelled"];
```

### 阶段 1：REST 拉历史 + 合并去重

```typescript
const page = await api.listEvents(runId);
setEvents(prev => {
  const seen = new Set(prev.map(e => e.id));
  const merged = [...prev, ...page.items.filter(e => !seen.has(e.id))]
    .sort((a, b) => a.sequence - b.sequence);
  lastSeqRef.current = merged.length ? merged[merged.length - 1].sequence : 0;
  return merged;
});
```

- 用事件 `id` 去重（避免与后续 SSE 重复）。
- 按 `sequence` 排序。
- 维护 `lastSeqRef` 作为 SSE 的起点游标。

### 阶段 2：建立 SSE 长连接

只在**未到终态**且**历史已加载**时才建连：

```typescript
if (!runId || !runStatus || TERMINAL.includes(runStatus)) return;
if (!historyLoaded) return;
const es = new EventSource(sseUrl(runId, lastSeqRef.current));
```

`onmessage` 里再次按 `id` 去重，新事件追加并更新 `lastSeqRef`：

```typescript
es.onmessage = (msg) => {
  const ev = JSON.parse(msg.data) as RunEvent;
  setEvents(prev => {
    if (prev.some(e => e.id === ev.id)) {
      lastSeqRef.current = Math.max(lastSeqRef.current, ev.sequence);
      return prev;
    }
    const next = [...prev, ev];
    lastSeqRef.current = ev.sequence;
    return next;
  });
};
```

无法解析的消息直接忽略（`try/catch`）。

### 阶段 3：到达终态自动关闭

```typescript
useEffect(() => {
  if (runStatus && TERMINAL.includes(runStatus)) {
    esRef.current?.close();
    esRef.current = null;
  }
}, [runStatus]);
```

连接释放通过 effect cleanup 的 `es.close()` 保证。

## 4. 断线重连策略

- **不加自定义重连**：`EventSource` 自带自动重连，`onerror` 里不主动 close（避免打断原生重连）。
- 重连时会带上 `?after_sequence=lastSeqRef.current`，后端只推游标之后的事件，配合前端按 `id` 去重，保证**不丢、不重**。
- 终态后由上层关闭连接，停止无意义的重连。

## 5. 附带一个节流 hook

`useRunEvents.ts` 里还导出了 `useThrottle`，用于高频更新（如进行中的状态）限流渲染，避免每帧都重渲染。

## 6. Timeline 渲染（`RunTimeline.tsx`）

- **图标**：按事件类型映射 SVG（step 加减号、完成对勾、agent 气泡、artifact 文档、run 完成/失败/取消等）。
- **颜色**：按事件名关键词着色——`failed` 红、`cancelled` 灰、`completed` 绿、`message` 强调色。
- **live 高亮**：当某事件 `sequence` 等于最后一个事件时打 `dot-live` 类，配合底部"监听中…"指示实时状态。
- **payload 渲染优先级**：`content`（Agent 正文）→ step 的 `name` → `artifact_id`（产物链）→ `error`（错误）→ 其余字段 JSON 格式化展示。

## 7. 已知取舍与改进方向

- **SSE 用浏览器原生 `EventSource`**：只支持 GET + 单向，无法认证头。若后端需要鉴权，需改用 `fetch` + `ReadableStream` 或 WebSocket。
- **依赖 `runStatus` 是否到终态来控制开关**：若 run 状态是"进行中但不产生新事件"，连接会一直挂着，可加 idle 超时。
- **events 全量存在组件 state**：长 run 事件很多时内存和渲染压力大，可考虑虚拟列表或分页。