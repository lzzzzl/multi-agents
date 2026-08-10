"use client";

import ReactMarkdown from "react-markdown";
import type { Artifact } from "@/lib/types";

/**
 * 按 artifact 类型渲染内容:
 * - markdown: 渲染为富文本
 * - json: 语法高亮展示(等宽字体)
 * - 其他: 纯文本
 */
export function ArtifactViewer({ artifact }: { artifact: Artifact }) {
  const content = artifact.content;

  if (!content) {
    return (
      <div className="text-sm text-muted">
        产物存储于{" "}
        <span className="font-mono text-xs">{artifact.storage_url ?? "外部存储"}</span>
      </div>
    );
  }

  if (artifact.type === "json") {
    return (
      <pre className="overflow-x-auto rounded-xl bg-ink p-4 font-mono text-xs leading-relaxed text-[#e8e8e8]">
        {content}
      </pre>
    );
  }

  if (artifact.type === "markdown" || artifact.mime_type === "text/markdown") {
    return (
      <article className="md-body">
        <ReactMarkdown>{content}</ReactMarkdown>
      </article>
    );
  }

  return (
    <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-zinc-bg p-4 font-mono text-xs text-muted">
      {content}
    </pre>
  );
}