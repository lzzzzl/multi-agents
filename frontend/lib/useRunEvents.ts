"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, sseUrl } from "@/lib/api";
import type { RunEvent, RunStatus } from "@/lib/types";

const TERMINAL: RunStatus[] = ["completed", "failed", "cancelled"];

/**
 * 订阅 run 的实时事件流。
 * 1. 先用 REST 拉取历史事件（含 after_sequence 增量）
 * 2. 再通过 EventSource 建立 SSE 长连接，收到新事件后追加
 * 3. less 到终态或组件卸载时关闭连接
 */
export function useRunEvents(runId: string, runStatus: RunStatus | undefined) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const lastSeqRef = useRef(0);
  const esRef = useRef<EventSource | null>(null);

  // 拉取历史事件
  useEffect(() => {
    if (!runId || !runStatus) return;
    let cancelled = false;

    (async () => {
      try {
        const page = await api.listEvents(runId);
        if (cancelled) return;
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => e.id));
          const merged = [...prev, ...page.items.filter((e) => !seen.has(e.id))].sort(
            (a, b) => a.sequence - b.sequence,
          );
          lastSeqRef.current = merged.length ? merged[merged.length - 1].sequence : 0;
          return merged;
        });
      } finally {
        if (!cancelled) setHistoryLoaded(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [runId, runStatus]);

  // 建立 SSE 连接（仅当未到终态）
  useEffect(() => {
    if (!runId || !runStatus || TERMINAL.includes(runStatus)) return;
    if (!historyLoaded) return;

    const es = new EventSource(sseUrl(runId, lastSeqRef.current));
    esRef.current = es;

    // 后端发送的是命名事件 "run_event"(sse-starlette 的 event 字段),
    // 必须用 addEventListener 监听,而非 onmessage(后者只收默认无名事件)。
    const onEvent = (msg: MessageEvent) => {
      try {
        const ev = JSON.parse(msg.data) as RunEvent;
        setEvents((prev) => {
          if (prev.some((e) => e.id === ev.id)) {
            lastSeqRef.current = Math.max(lastSeqRef.current, ev.sequence);
            return prev;
          }
          const next = [...prev, ev];
          lastSeqRef.current = ev.sequence;
          return next;
        });
      } catch {
        // 忽略无法解析的消息
      }
    };
    es.addEventListener("run_event", onEvent);

    es.onerror = () => {
      // EventSource 会自动重连；终态后由上层关闭
    };

    return () => {
      es.removeEventListener("run_event", onEvent);
      es.close();
      esRef.current = null;
    };
  }, [runId, runStatus, historyLoaded]);

  // 到达终态后关闭连接
  useEffect(() => {
    if (runStatus && TERMINAL.includes(runStatus)) {
      esRef.current?.close();
      esRef.current = null;
    }
  }, [runStatus]);

  return { events };
}

export function useThrottle<T>(value: T, ms: number): T {
  const [throttled, setThrottled] = useState(value);
  const lastRun = useRef(0);

  useEffect(() => {
    const now = Date.now();
    if (now - lastRun.current >= ms) {
      lastRun.current = now;
      setThrottled(value);
      return;
    }
    const timer = setTimeout(() => {
      lastRun.current = Date.now();
      setThrottled(value);
    }, ms - (now - lastRun.current));
    return () => clearTimeout(timer);
  }, [value, ms]);

  return throttled;
}