"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { formatDateTime, shortId } from "@/lib/format";
import { useRunEvents } from "@/lib/useRunEvents";
import { StatusBadge } from "@/components/StatusBadge";
import { RunTimeline } from "@/components/RunTimeline";
import { ArtifactViewer } from "@/components/ArtifactViewer";
import type { Artifact, RunStatus } from "@/lib/types";

const TERMINAL: RunStatus[] = ["completed", "failed", "cancelled"];

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;

  const { data: run, isLoading, isError, error } = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId),
    enabled: !!runId,
    refetchInterval: (query) => {
      const status = (query.state.data as { status?: RunStatus } | undefined)?.status;
      return status && !TERMINAL.includes(status) ? 2000 : false;
    },
  });

  const { data: artifacts } = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => api.listRunArtifacts(runId),
    enabled: !!runId,
  });

  const artifactList = artifacts?.items ?? [];
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null);
  const activeArtifact =
    artifactList.find((a) => a.id === activeArtifactId) ?? artifactList[0] ?? null;

  const { events } = useRunEvents(runId, run?.status);
  const live = !!run && !TERMINAL.includes(run.status);

  const cancelMutation = useMutation({
    mutationFn: () => api.cancelRun(runId),
    onError: (e) => alert(e instanceof Error ? e.message : "取消失败"),
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-6xl px-5 py-10">
        <div className="h-8 w-1/3 animate-pulse rounded bg-line" />
        <div className="mt-6 grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="h-96 animate-pulse rounded-2xl border border-line bg-surface lg:col-span-2" />
          <div className="h-96 animate-pulse rounded-2xl border border-line bg-surface" />
        </div>
      </div>
    );
  }

  if (isError || !run) {
    return (
      <div className="mx-auto max-w-6xl px-5 py-10">
        <div className="rounded-xl border border-red-bg bg-red-bg/60 p-5 text-sm text-red">
          {error instanceof Error ? error.message : "运行不存在"}
        </div>
      </div>
    );
  }

  const cost = run.cost_summary;

  return (
    <div className="mx-auto max-w-6xl px-5 py-10">
      {/* 顶部信息 */}
      <div className="mb-6">
        <Link
          href={`/tasks/${run.task_id}`}
          className="mb-3 inline-flex items-center gap-1 text-sm text-muted transition-colors hover:text-accent"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
            <path d="m15 18-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          返回任务
        </Link>

        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-display text-3xl font-semibold tracking-tight">
              运行 <span className="font-mono text-2xl text-muted">{shortId(run.id)}</span>
            </h1>
            <StatusBadge status={run.status} />
          </div>

          {live && (
            <button
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
              className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-4 py-2 text-sm font-semibold text-red transition-colors hover:bg-red-bg"
            >
              <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
              {cancelMutation.isPending ? "取消中…" : "取消运行"}
            </button>
          )}
        </div>

        {/* meta 行 */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <MetaChip label="Workflow">
            <span className="font-mono text-xs">{run.workflow_name}</span>
          </MetaChip>
          <MetaChip label="开始时间">{formatDateTime(run.started_at)}</MetaChip>
          <MetaChip label="结束时间">{formatDateTime(run.completed_at ?? run.failed_at ?? run.cancelled_at)}</MetaChip>
          <MetaChip label="成本">
            {cost ? (
              <span>
                ${cost.estimated_cost?.toFixed(4) ?? "—"}
                <span className="ml-1 text-xs text-faint">({cost.input_tokens ?? 0} in / {cost.output_tokens ?? 0} out)</span>
              </span>
            ) : (
              "—"
            )}
          </MetaChip>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        {/* 左：steps + 事件流 */}
        <div className="space-y-5 lg:col-span-2">
          {run.steps.length > 0 && (
            <div className="rounded-2xl border border-line bg-surface p-5">
              <h2 className="mb-3 font-display text-base font-semibold tracking-tight">执行步骤</h2>
              <div className="flex flex-wrap gap-2">
                {[...run.steps]
                  .sort((a, b) => a.sequence - b.sequence)
                  .map((s) => (
                    <div
                      key={s.id}
                      className="flex items-center gap-2 rounded-lg border border-line bg-background px-3 py-1.5 text-sm"
                    >
                      <span className="font-mono text-[11px] text-faint">{s.sequence}</span>
                      <span className="font-medium">{s.name}</span>
                      <StepDot status={s.status} />
                    </div>
                  ))}
              </div>
            </div>
          )}

          <div className="rounded-2xl border border-line bg-surface p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-display text-base font-semibold tracking-tight">事件流</h2>
              <span className="font-mono text-xs text-faint">{events.length} 条</span>
            </div>
            <RunTimeline events={events} live={live} />
          </div>
        </div>

        {/* 右：产物列表 + viewer */}
        <div className="rounded-2xl border border-line bg-surface lg:sticky lg:top-20 lg:self-start">
          <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
            <h2 className="font-display text-base font-semibold tracking-tight">产物</h2>
            {activeArtifact && (
              <span className="font-mono text-[11px] text-faint">
                {activeArtifact.type} · {activeArtifact.size_bytes ?? 0} B
              </span>
            )}
          </div>

          {/* 产物切换列表 */}
          {artifactList.length > 1 && (
            <div className="flex flex-wrap gap-1.5 border-b border-line px-5 py-3">
              {artifactList.map((a) => (
                <button
                  key={a.id}
                  onClick={() => setActiveArtifactId(a.id)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                    activeArtifact?.id === a.id
                      ? "bg-accent text-white"
                      : "border border-line bg-background text-muted hover:text-ink"
                  }`}
                >
                  {a.type === "json" ? "摘要" : "报告"}
                </button>
              ))}
            </div>
          )}

          <div className="p-5">
            {!activeArtifact ? (
              <div className="py-10 text-center text-sm text-faint">
                {live ? "运行完成后将在此生成产物…" : "无产物"}
              </div>
            ) : (
              <>
                <div className="mb-3 flex items-center justify-between">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{activeArtifact.name}</div>
                  </div>
                  <Link
                    href={`/artifacts/${activeArtifact.id}`}
                    className="ml-3 inline-flex shrink-0 items-center gap-1 text-xs font-medium text-accent transition-colors hover:text-accent-strong"
                  >
                    新窗口打开
                  </Link>
                </div>
                <ArtifactViewer artifact={activeArtifact} />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StepDot({ status }: { status: string }) {
  const color =
    status === "completed"
      ? "var(--green)"
      : status === "failed"
        ? "var(--red)"
        : status === "cancelled"
          ? "var(--zinc)"
          : "var(--accent)";
  const live = status === "running";
  return (
    <span
      className={`h-2 w-2 rounded-full ${live ? "dot-live" : ""}`}
      style={{ background: color }}
    />
  );
}

function MetaChip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-surface px-4 py-3">
      <div className="text-xs text-faint">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-ink">{children}</div>
    </div>
  );
}