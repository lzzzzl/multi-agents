"use client";

import type { RunEvent } from "@/lib/types";
import { formatDateTime } from "@/lib/format";

interface TimelineProps {
  events: RunEvent[];
  live: boolean;
}

function EventIcon({ type }: { type: string }) {
  const common = { className: "h-3.5 w-3.5", fill: "none", stroke: "currentColor", strokeWidth: 2 };
  switch (type) {
    case "step_started":
    case "agent_started":
      return (
        <svg viewBox="0 0 24 24" {...common}>
          <path d="M12 5v14M5 12h14" strokeLinecap="round" />
        </svg>
      );
    case "step_completed":
      return (
        <svg viewBox="0 0 24 24" {...common}>
          <path d="m5 13 4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "agent_message":
      return (
        <svg viewBox="0 0 24 24" {...common}>
          <path d="M8 10h8M8 14h5" strokeLinecap="round" />
          <path d="M21 12a9 9 0 0 1-9 9H5l-2 2V12a9 9 0 0 1 18 0Z" strokeLinejoin="round" />
        </svg>
      );
    case "artifact_created":
      return (
        <svg viewBox="0 0 24 24" {...common}>
          <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2" strokeLinecap="round" />
        </svg>
      );
    case "run_completed":
      return (
        <svg viewBox="0 0 24 24" {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="m8.5 12.5 2.5 2.5 5-5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    case "run_failed":
      return (
        <svg viewBox="0 0 24 24" {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M9 9l6 6M15 9l-6 6" strokeLinecap="round" />
        </svg>
      );
    case "run_cancelled":
      return (
        <svg viewBox="0 0 24 24" {...common}>
          <rect x="5" y="5" width="14" height="14" rx="2" />
          <path d="M9 9h6v6H9z" />
        </svg>
      );
    default:
      return (
        <svg viewBox="0 0 24 24" {...common}>
          <circle cx="12" cy="12" r="4" />
        </svg>
      );
  }
}

function typeLabel(type: string): string {
  const map: Record<string, string> = {
    step_started: "步骤开始",
    step_completed: "步骤完成",
    agent_started: "Agent 开始",
    agent_message: "Agent 消息",
    artifact_created: "产物已生成",
    run_started: "运行开始",
    run_completed: "运行完成",
    run_failed: "运行失败",
    run_cancelled: "运行已取消",
    tool_call: "工具调用",
  };
  return map[type] ?? type;
}

function eventColor(type: string): string {
  if (type.includes("failed")) return "var(--red)";
  if (type.includes("cancelled")) return "var(--zinc)";
  if (type.includes("completed")) return "var(--green)";
  if (type.includes("message")) return "var(--accent)";
  return "var(--accent-strong)";
}

export function RunTimeline({ events, live }: TimelineProps) {
  return (
    <div className="relative">
      {/* 纵向时间线 */}
      <div className="absolute inset-y-2 left-[7px] w-px bg-line" />

      <div className="space-y-1">
        {events.map((ev) => {
          const color = eventColor(ev.type);
          const isLive = live && ev.sequence === events[events.length - 1]?.sequence;
          return (
            <div key={ev.id} className="group relative flex gap-3.5 rounded-lg px-2 py-2 transition-colors hover:bg-zinc-bg/60">
              <span
                className={`relative z-10 mt-1 flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-full text-white ${isLive ? "dot-live" : ""}`}
                style={{ background: color }}
              >
                <EventIcon type={ev.type} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="text-sm font-semibold" style={{ color }}>
                    {ev.agent_id ? `${typeLabel(ev.type)} · ${ev.agent_id.replace("agent_", "")}` : typeLabel(ev.type)}
                  </span>
                  <span className="font-mono text-[11px] text-faint">
                    #{ev.sequence} · {formatDateTime(ev.created_at)}
                  </span>
                </div>
                {ev.payload && (
                  <div className="mt-1 text-sm text-muted">
                    {renderPayload(ev)}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {live && (
        <div className="relative z-10 mt-2 flex items-center gap-2 px-2 pt-2 text-sm text-accent">
          <span className="h-2 w-2 rounded-full bg-accent dot-live" />
          <span className="font-medium">监听中…</span>
        </div>
      )}
    </div>
  );
}

function renderPayload(ev: RunEvent): React.ReactNode {
  const p = ev.payload ?? {};
  if (p.content) return <p className="whitespace-pre-wrap">{String(p.content)}</p>;
  if (p.name && ev.type.includes("step")) {
    return <p>步骤「{String(p.name)}」</p>;
  }
  if (p.artifact_id) {
    return <p>产物 <span className="font-mono text-xs">{String(p.artifact_id)}</span> · {p.name ? String(p.name) : ""}</p>;
  }
  if (p.error) return <p className="text-red">{String(p.error)}</p>;
  const entries = Object.entries(p).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) return null;
  return (
    <pre className="overflow-x-auto rounded-lg bg-zinc-bg px-3 py-2 font-mono text-xs text-muted">
      {JSON.stringify(Object.fromEntries(entries), null, 2)}
    </pre>
  );
}