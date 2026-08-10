"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { ArtifactViewer } from "@/components/ArtifactViewer";

export default function ArtifactDetailPage() {
  const params = useParams<{ id: string }>();
  const artifactId = params.id;

  const { data: artifact, isLoading, isError, error } = useQuery({
    queryKey: ["artifact", artifactId],
    queryFn: () => api.getArtifact(artifactId),
    enabled: !!artifactId,
  });

  if (isLoading) {
    return (
      <div className="mx-auto max-w-4xl px-5 py-10">
        <div className="h-8 w-1/3 animate-pulse rounded bg-line" />
        <div className="mt-6 h-64 animate-pulse rounded-2xl border border-line bg-surface" />
      </div>
    );
  }

  if (isError || !artifact) {
    return (
      <div className="mx-auto max-w-4xl px-5 py-10">
        <div className="rounded-xl border border-red-bg bg-red-bg/60 p-5 text-sm text-red">
          {error instanceof Error ? error.message : "产物不存在"}
        </div>
      </div>
    );
  }

  const handleDownload = () => {
    const blob = new Blob([artifact.content ?? ""], {
      type: artifact.mime_type ?? "text/plain",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = artifact.name || "artifact";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-4xl px-5 py-10">
      <div className="mb-6">
        <Link
          href={`/runs/${artifact.run_id}`}
          className="mb-3 inline-flex items-center gap-1 text-sm text-muted transition-colors hover:text-accent"
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
            <path d="m15 18-6-6 6-6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          返回运行
        </Link>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="font-display text-2xl font-semibold tracking-tight">{artifact.name}</h1>
            <div className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm text-faint">
              <span>
                类型 <span className="font-mono text-muted">{artifact.type}</span>
              </span>
              <span>
                MIME <span className="font-mono text-muted">{artifact.mime_type ?? "—"}</span>
              </span>
              <span>
                大小 <span className="text-muted">{artifact.size_bytes ?? 0} B</span>
              </span>
              <span>
                创建于 <span className="text-muted">{formatDateTime(artifact.created_at)}</span>
              </span>
              {artifact.created_by_agent_id && (
                <span>
                  产出 Agent{" "}
                  <span className="font-mono text-muted">{artifact.created_by_agent_id}</span>
                </span>
              )}
            </div>
          </div>

          <button
            onClick={handleDownload}
            className="inline-flex shrink-0 items-center gap-2 rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-background transition-colors hover:bg-accent-strong"
          >
            <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
              <path d="M12 3v12m0 0 4-4m-4 4-4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            下载
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-line bg-surface p-5">
        <ArtifactViewer artifact={artifact} />
      </div>
    </div>
  );
}