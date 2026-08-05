"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Priority } from "@/lib/types";

const PRIORITIES: { key: Priority; label: string; hint: string }[] = [
  { key: "low", label: "低", hint: "低优先级" },
  { key: "normal", label: "普通", hint: "默认" },
  { key: "high", label: "高", hint: "高优先级" },
  { key: "urgent", label: "紧急", hint: "立即处理" },
];

export default function NewTaskPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<Priority>("normal");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.createTask({
        title: title.trim(),
        description: description.trim() || null,
        priority,
      }),
    onSuccess: (task) => {
      router.push(`/tasks/${task.id}`);
    },
    onError: (e) => setError(e instanceof Error ? e.message : "创建失败"),
  });

  const canSubmit = title.trim().length > 0 && !mutation.isPending;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (canSubmit) mutation.mutate();
  }

  return (
    <div className="mx-auto max-w-2xl px-5 py-10">
      <div className="mb-8">
        <div className="text-sm font-semibold uppercase tracking-widest text-accent">
          Create
        </div>
        <h1 className="mt-1 font-display text-3xl font-semibold tracking-tight">新建任务</h1>
        <p className="mt-1 text-sm text-muted">
          描述你的目标，创建后即可启动 multi-agent 运行。
        </p>
      </div>

      <form
        onSubmit={onSubmit}
        className="animate-rise space-y-6 rounded-2xl border border-line bg-surface p-6"
      >
        <div>
          <label htmlFor="title" className="mb-1.5 block text-sm font-semibold">
            任务标题 <span className="text-red">*</span>
          </label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：生成一份 2026 上半年市场分析报告"
            autoFocus
            className="w-full rounded-xl border border-line bg-background px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
        </div>

        <div>
          <label htmlFor="description" className="mb-1.5 block text-sm font-semibold">
            任务描述
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="补充背景、目标或约束（可选）"
            rows={4}
            className="w-full resize-none rounded-xl border border-line bg-background px-4 py-2.5 text-sm outline-none transition-colors placeholder:text-faint focus:border-accent focus:ring-2 focus:ring-accent/20"
          />
        </div>

        <div>
          <div className="mb-1.5 text-sm font-semibold">优先级</div>
          <div className="grid grid-cols-4 gap-2">
            {PRIORITIES.map((p) => (
              <button
                key={p.key}
                type="button"
                onClick={() => setPriority(p.key)}
                className={`rounded-xl border px-3 py-2.5 text-sm font-medium transition-colors ${
                  priority === p.key
                    ? "border-accent bg-accent/5 text-accent-strong"
                    : "border-line bg-background text-muted hover:text-ink"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="rounded-lg border border-red-bg bg-red-bg/60 px-4 py-2.5 text-sm text-red">
            {error}
          </div>
        )}

        <div className="flex items-center gap-3 pt-1">
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 rounded-full bg-ink px-6 py-2.5 text-sm font-semibold text-background transition-colors hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-40"
          >
            {mutation.isPending ? "创建中…" : "创建任务"}
          </button>
          <button
            type="button"
            onClick={() => router.back()}
            className="rounded-full px-4 py-2.5 text-sm font-medium text-muted transition-colors hover:text-ink"
          >
            取消
          </button>
        </div>
      </form>
    </div>
  );
}