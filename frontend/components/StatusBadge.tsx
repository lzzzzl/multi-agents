import type { RunStatus, TaskStatus } from "@/lib/types";

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  pending: { label: "待执行", color: "var(--amber)", bg: "var(--amber-bg)" },
  running: { label: "运行中", color: "var(--accent)", bg: "rgba(15,118,110,0.10)" },
  completed: { label: "已完成", color: "var(--green)", bg: "var(--green-bg)" },
  failed: { label: "失败", color: "var(--red)", bg: "var(--red-bg)" },
  cancelled: { label: "已取消", color: "var(--zinc)", bg: "var(--zinc-bg)" },
};

export function StatusBadge({ status }: { status: TaskStatus | RunStatus }) {
  const meta = STATUS_META[status] ?? { label: status, color: "var(--zinc)", bg: "var(--zinc-bg)" };
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold"
      style={{ color: meta.color, background: meta.bg }}
    >
      <span
        className={`h-1.5 w-1.5 rounded-full ${status === "running" ? "dot-live" : ""}`}
        style={{ background: meta.color }}
      />
      {meta.label}
    </span>
  );
}