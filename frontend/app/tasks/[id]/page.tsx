"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatDateTime, shortId } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";

export default function TaskDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const taskId = params.id;

  const { data: task, isLoading, isError, error } = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api.getTask(taskId),
    enabled: !!taskId,
  });

  const runMutation = useMutation({
    mutationFn: () => api.createRun({ task_id: taskId }),
    onSuccess: (run) => router.push(`/runs/${run.id}`),
    onError: (e) => alert(e instanceof Error ? e.message : "启动失败"),
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-5 py-10">
        <div className="h-8 w-1/3 animate-pulse rounded bg-line" />
        <div className="mt-6 h-40 animate-pulse rounded-2xl border border-line bg-surface" />
      </div>
    );
  }

  if (isError || !task) {
    return (
      <div className="mx-auto max-w-4xl px-5 py-10">
        <div className="rounded-xl border border-red-bg bg-red-bg/60 p-5 text-sm text-red">
          {error instanceof Error ? error.message : "任务不存在"}
        </div>
      </div>
    );
  }

  const runs = [...task.runs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );

  return (
    <div className="mx-auto max-w-4xl px-5 py-10">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/tasks"
            className="mb-3 inline-flex items-center gap-1 text-sm text-muted transition-colors hover:text-accent"
          >
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
              <path d="m15 18-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            返回任务列表
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-3xl font-semibold tracking-tight">{task.title}</h1>
            <StatusBadge status={task.status} />
          </div>
          {task.description && <p className="mt-2 text-muted">{task.description}</p>}
          <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-sm text-faint">
            <span>
              ID <span className="font-mono text-muted">{task.id}</span>
            </span>
            <span>
              优先级 <span className="font-medium capitalize text-muted">{task.priority}</span>
            </span>
            <span>
              创建于 <span className="text-muted">{formatDateTime(task.created_at)}</span>
            </span>
          </div>
        </div>

        <button
          onClick={() => runMutation.mutate()}
          disabled={runMutation.isPending}
          className="inline-flex items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-background transition-colors hover:bg-accent-strong disabled:opacity-40"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
            <path d="M8 5.14v13.72a1 1 0 0 0 1.5.86l11-6.86a1 1 0 0 0 0-1.72l-11-6.86a1 1 0 0 0-1.5.86Z" strokeLinejoin="round" />
          </svg>
          {runMutation.isPending ? "启动中…" : "启动运行"}
        </button>
      </div>

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold tracking-tight">
          运行记录
          <span className="ml-2 text-sm font-normal text-faint">{runs.length} 次</span>
        </h2>

        {runs.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-line bg-surface/60 px-6 py-12 text-center">
            <p className="text-sm text-muted">该任务还没有运行过，点击右上角「启动运行」开始。</p>
          </div>
        ) : (
          <div className="space-y-2.5">
            {runs.map((r, i) => (
              <Link
                key={r.id}
                href={`/runs/${r.id}`}
                className="group flex items-center gap-4 rounded-xl border border-line bg-surface px-5 py-4 transition-all hover:border-accent/40 hover:shadow-md hover:shadow-ink/5"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2.5">
                    <span className="font-mono text-xs text-faint">#{runs.length - i}</span>
                    <span className="font-mono text-sm">{shortId(r.id)}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  <div className="mt-1 text-sm text-muted">
                    workflow：<span className="font-mono text-xs">{r.workflow_name}</span>
                  </div>
                </div>
                <div className="hidden text-right text-sm text-muted md:block">
                  <div className="text-xs text-faint">创建于</div>
                  <div>{formatDateTime(r.created_at)}</div>
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
            ))}
          </div>
        )}
      </div>
    </div>
  );
}