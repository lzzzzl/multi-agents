import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ArtifactViewer } from "@/components/ArtifactViewer";
import type { Artifact } from "@/lib/types";


function artifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: "artifact_1",
    run_id: "run_1",
    step_id: null,
    created_by_agent_id: null,
    type: "markdown",
    name: "a.md",
    mime_type: "text/markdown",
    content: "# 标题",
    storage_url: null,
    size_bytes: 8,
    metadata: null,
    created_at: "2026-08-13T00:00:00Z",
    ...overrides,
  };
}


describe("ArtifactViewer", () => {
  it("渲染 markdown 内容", () => {
    render(<ArtifactViewer artifact={artifact({ content: "# 标题" })} />);
    expect(screen.getByRole("heading", { name: "标题" })).toBeInTheDocument();
  });

  it("渲染 json 内容为等宽文本", () => {
    render(<ArtifactViewer artifact={artifact({ type: "json", content: '{"a":1}' })} />);
    expect(screen.getByText('{"a":1}')).toBeInTheDocument();
  });

  it("无内容时显示存储地址", () => {
    render(
      <ArtifactViewer
        artifact={artifact({ content: null, storage_url: "s3://bucket/key" })}
      />,
    );
    expect(screen.getByText("s3://bucket/key")).toBeInTheDocument();
  });
});
