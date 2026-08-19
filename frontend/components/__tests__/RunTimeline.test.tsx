import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunTimeline } from "@/components/RunTimeline";
import type { RunEvent } from "@/lib/types";


function ev(overrides: Partial<RunEvent> = {}): RunEvent {
  return {
    id: "evt_1",
    run_id: "run_1",
    step_id: null,
    agent_id: null,
    tool_call_id: null,
    type: "run_started",
    sequence: 1,
    payload: null,
    created_at: "2026-08-13T00:00:00Z",
    ...overrides,
  };
}


describe("RunTimeline", () => {
  it("渲染事件类型标签", () => {
    render(<RunTimeline events={[ev({ type: "run_completed" })]} live={false} />);
    expect(screen.getByText("运行完成")).toBeInTheDocument();
  });

  it("渲染 agent 消息并显示内容", () => {
    render(
      <RunTimeline
        events={[
          ev({
            type: "agent_message",
            agent_id: "agent_writer",
            payload: { content: "你好" },
          }),
        ]}
        live={false}
      />,
    );
    expect(screen.getByText(/Agent 消息/)).toBeInTheDocument();
    expect(screen.getByText("你好")).toBeInTheDocument();
  });

  it("live 时显示监听提示", () => {
    render(<RunTimeline events={[ev()]} live={true} />);
    expect(screen.getByText("监听中…")).toBeInTheDocument();
  });

  it("llm_token 事件折叠为实时输出块并累积文本", () => {
    render(
      <RunTimeline
        events={[
          ev({ id: "e1", type: "step_started", step_id: "s1", agent_id: "agent_writer", sequence: 1 }),
          ev({ id: "e2", type: "llm_token", step_id: "s1", agent_id: "agent_writer", sequence: 2, payload: { delta: "# 标题\n\n" } }),
          ev({ id: "e3", type: "llm_token", step_id: "s1", agent_id: "agent_writer", sequence: 3, payload: { delta: "## 正文" } }),
        ]}
        live={true}
      />,
    );
    // token 事件不单独成行,聚合成一块实时输出
    expect(screen.getByText("writer 正在输出…")).toBeInTheDocument();
    // testing-library 默认规范化空白,用 textContent 校验原始累积文本
    const pre = screen.getByText("writer 正在输出…").closest("div")?.parentElement?.querySelector("pre");
    expect(pre?.textContent).toContain("# 标题\n\n## 正文▍");
    expect(screen.queryByText("LLM 调用")).not.toBeInTheDocument();
  });

  it("步骤完成后隐藏对应实时输出块", () => {
    render(
      <RunTimeline
        events={[
          ev({ id: "e1", type: "step_started", step_id: "s1", agent_id: "agent_writer", sequence: 1 }),
          ev({ id: "e2", type: "llm_token", step_id: "s1", agent_id: "agent_writer", sequence: 2, payload: { delta: "# 草稿" } }),
          ev({ id: "e3", type: "step_completed", step_id: "s1", agent_id: "agent_writer", sequence: 3 }),
        ]}
        live={true}
      />,
    );
    expect(screen.queryByText("writer 正在输出…")).not.toBeInTheDocument();
    const pre2 = document.querySelector("pre.stream-text");
    expect(pre2).toBeNull();
  });
});
