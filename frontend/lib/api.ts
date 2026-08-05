import type {
  ApiResponse,
  Artifact,
  Page,
  Run,
  RunDetail,
  RunEventPage,
  Task,
  TaskCreate,
  TaskDetail,
} from "./types";

// 后端 API 基地址。默认本地开发后端在 8000 端口。
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiClientError extends Error {
  code: string;
  details?: Record<string, unknown> | null;
  constructor(code: string, message: string, details?: Record<string, unknown> | null) {
    super(message);
    this.name = "ApiClientError";
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
    cache: "no-store",
  });

  let body: ApiResponse<T> | null = null;
  try {
    body = (await res.json()) as ApiResponse<T>;
  } catch {
    // 非 JSON 响应
  }

  if (!res.ok || !body || body.error) {
    const err = body?.error;
    throw new ApiClientError(err?.code ?? "HTTP_ERROR", err?.message ?? `请求失败 (${res.status})`, err?.details);
  }

  return body.data as T;
}

export const api = {
  // health
  health: () => request<{ status: string }>("/api/health"),

  // tasks
  listTasks: (params?: { status?: string; limit?: number; cursor?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    if (params?.limit) q.set("limit", String(params.limit));
    if (params?.cursor) q.set("cursor", params.cursor);
    const qs = q.toString();
    return request<Page<Task>>(`/api/tasks${qs ? `?${qs}` : ""}`);
  },
  getTask: (id: string) => request<TaskDetail>(`/api/tasks/${id}`),
  createTask: (payload: TaskCreate) =>
    request<Task>(`/api/tasks`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // runs
  createRun: (payload: { task_id: string; workflow_name?: string; input_override?: Record<string, unknown> | null }) =>
    request<Run>(`/api/runs`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  getRun: (id: string) => request<RunDetail>(`/api/runs/${id}`),
  cancelRun: (id: string) =>
    request<Run>(`/api/runs/${id}/cancel`, { method: "POST", body: "{}" }),
  listEvents: (runId: string, afterSequence?: number) => {
    const q = afterSequence ? `?after_sequence=${afterSequence}` : "";
    return request<RunEventPage>(`/api/runs/${runId}/events${q}`);
  },

  // artifacts
  listRunArtifacts: (runId: string) =>
    request<Page<Artifact>>(`/api/runs/${runId}/artifacts`),
  getArtifact: (id: string) => request<Artifact>(`/api/artifacts/${id}`),
};

// SSE 事件流地址
export function sseUrl(runId: string, afterSequence?: number): string {
  const q = afterSequence ? `?after_sequence=${afterSequence}` : "";
  return `${API_BASE}/api/runs/${runId}/events/stream${q}`;
}