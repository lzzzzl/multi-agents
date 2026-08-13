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
});
