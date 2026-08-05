"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import type { Task, TaskStatus } from "@/lib/types";
import { formatRelative, shortId } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";

const FILTERS: { key: string; label: string }[] = [
  { key: "", label: "全部" },
  { key: "pending", label: "待执行" },
  { key: "running", label: "运行中" },
  { key: "completed", label: "已完成" },
  { key: "failed", label: "失败" },
];

const PRIORITY_ORDER: Record<string, number> = { urgent: 0, high: 1, normal: 2, low: 3 };

function TaskRow({ task }: { task: Task }) {
  return (
    <Link
      href={`/tasks/${task.id}`}
      className="group flex items-center gap-5 rounded-xl border border-line bg-surface px-5 py-4 transition-all hover:border-accent/40 hover:shadow-md hover:shadow-ink/5"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5">
          <h3 className="truncate font-display text-base font-semibold tracking-tight group-hover:text-accent-strong">
            {task.title}
          </h3>
          <StatusBadge status={task.status} />
        </div>
        {task.description && (
          <p className="mt-1 truncate text-sm text-muted">{task.description}</p>
        )}
      </div>

      <div className="hidden shrink-0 items-center gap-6 text-right text-sm text-muted md:flex">
        <div>
          <div className="text-xs text-faint">优先级</div>
          <div className="font-medium capitalize">{task.priority}</div>
        </div>
        <div>
          <div className="text-xs text-faint">ID</div>
          <div className="font-mono text-xs">{shortId(task.id)}</div>
        </div>
        <div>
          <div className="text-xs text-faint">创建</div>
          <div>{formatRelative(task.created_at)}</div>
        </div>
      </div>

      <svg
        viewBox="0 0 24 24"
        fill="none"
        className="h-4 w-4 shrink-0 text-faint transition-transform group-hover:translate-x-0.5 group-hover:text-accent"
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="m9 18 6-6-6-6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </Link>
  );
}

export default function TaskListPage() {
  const [status, setStatus] = useState<string>("");

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["tasks", status],
    queryFn: () => api.listTasks(status ? { status } : {}),
    placeholderData: (prev) => prev,
  });

  const tasks = data?.items ?? [];
  const sorted = [...tasks].sort((a, b) => {
    // 运行中的排前面，然后按优先级、时间
    const order = { running: 0, pending: 1, failed: 2, completed: 3, cancelled: 4 };
    const s = (order[a.status as TaskStatus] ?? 9) - (order[b.status as TaskStatus] ?? 9);
    if (s !== 0) return s;
    const p = (PRIORITY_ORDER[a.priority] ?? 9) - (PRIORITY_ORDER[b.priority] ?? 9);
    if (p !== 0) return p;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });

  return (
    <div className="mx-auto max-w-6xl px-5 py-10">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-sm font-semibold uppercase tracking-widest text-accent">
            Workbench
          </div>
          <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight">
            任务列表
          </h1>
          <p className="mt-1 text-sm text-muted">
            创建并管理 multi-agent 任务，跟踪每一次运行。
          </p>
        </div>
        <Link
          href="/tasks/new"
          className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-background transition-colors hover:bg-accent-strong"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2.5">
            <path d="M12 5v14M5 12h14" strokeLinecap="round" />
          </svg>
          新建任务
        </Link>
      </div>

      <div className="mb-5 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setStatus(f.key)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
              status === f.key
                ? "bg-accent text-white"
                : "border border-line bg-surface text-muted hover:text-ink"
            }`}
          >
            {f.label}
            {f.key !== "" && (
              <span className={`ml-1.5 text-xs ${status === f.key ? "text-white/70" : "text-faint"}`}>
                {tasks.filter((t) => t.status === f.key).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl border border-line bg-surface" />
          ))}
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-red-bg bg-red-bg/60 p-5 text-sm text-red">
          加载失败：{error instanceof Error ? error.message : "未知错误"}
        </div>
      )}

      {!isLoading && !isError && sorted.length === 0 && (
        <div className="rounded-2xl border border-dashed border-line bg-surface/60 px-6 py-16 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent">
            <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6" stroke="currentColor" strokeWidth="1.8">
              <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2" strokeLinecap="round" />
            </svg>
          </div>
          <h3 className="font-display text-lg font-semibold">还没有任务</h3>
          <p className="mt-1 text-sm text-muted">创建第一个任务，开始 multi-agent 工作流。</p>
          <Link
            href="/tasks/new"
            className="mt-4 inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2 text-sm font-semibold text-background transition-colors hover:bg-accent-strong"
          >
            新建任务
          </Link>
        </div>
      )}

      <div className="space-y-3">
        {sorted.map((t, i) => (
          <div key={t.id} className="animate-rise" style={{ animationDelay: `${i * 40}ms` }}>
            <TaskRow task={t} />
          </div>
        ))}
      </div>
    </div>
  );
}