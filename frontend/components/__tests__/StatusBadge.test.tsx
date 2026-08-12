import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusBadge } from "@/components/StatusBadge";

describe("StatusBadge smoke", () => {
  it("渲染运行状态标签", () => {
    render(<StatusBadge status="running" />);
    expect(screen.getByText("运行中")).toBeInTheDocument();
  });

  it("渲染终态标签", () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText("已完成")).toBeInTheDocument();
  });

  it("未知状态回退为原文", () => {
    render(<StatusBadge status="unknown_x" />);
    expect(screen.getByText("unknown_x")).toBeInTheDocument();
  });
});