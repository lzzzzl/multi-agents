// 与后端 schemas 对齐的 TypeScript 类型定义

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

export interface ApiResponse<T> {
  data: T | null;
  error: ApiError | null;
}

export interface Page<T> {
  items: T[];
  next_cursor: string | null;
}

// ---- Task ----
// 与后端对齐: draft(草稿) / queued(已入队) / running / completed / failed / cancelled / archived
export type TaskStatus =
  | "draft"
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "archived";
export type Priority = "low" | "normal" | "high" | "urgent";

export interface Task {
  id: string;
  project_id: string | null;
  created_by: string | null;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: Priority;
  input: Record<string, unknown> | null;
  metadata: Record<string, unknown> | null;
  latest_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  description?: string | null;
  input?: Record<string, unknown> | null;
  priority?: Priority;
  metadata?: Record<string, unknown> | null;
}

export interface TaskRunSummary {
  id: string;
  status: RunStatus;
  workflow_name: string;
  created_at: string;
}

export interface TaskDetail extends Task {
  runs: TaskRunSummary[];
}

// ---- Run ----
// 与后端对齐: queued / running / waiting_for_approval / completed / failed / cancelled
export type RunStatus =
  | "queued"
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "failed"
  | "cancelled";
export type RunStepStatus = "pending" | "running" | "completed" | "failed" | "cancelled" | "skipped" | "waiting_for_approval";

export interface Run {
  id: string;
  task_id: string;
  workflow_name: string;
  workflow_version: string;
  status: RunStatus;
  started_at: string | null;
  completed_at: string | null;
  failed_at: string | null;
  cancelled_at: string | null;
  error_message: string | null;
  cost_summary: { input_tokens?: number; output_tokens?: number; estimated_cost?: number } | null;
  source_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface RunCreate {
  task_id: string;
  workflow_name?: string;
  input_override?: Record<string, unknown> | null;
}

export interface RunStep {
  id: string;
  run_id: string;
  agent_id: string | null;
  name: string;
  type: string;
  status: RunStepStatus;
  sequence: number;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}

export interface RunDetail extends Run {
  steps: RunStep[];
}

// ---- RunEvent ----
export type EventType =
  | "step_started"
  | "step_completed"
  | "agent_started"
  | "agent_message"
  | "artifact_created"
  | "run_started"
  | "run_completed"
  | "run_failed"
  | "run_cancelled"
  | "tool_call"
  | string;

export interface RunEvent {
  id: string;
  run_id: string;
  step_id: string | null;
  agent_id: string | null;
  tool_call_id: string | null;
  type: EventType;
  sequence: number;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface RunEventPage {
  items: RunEvent[];
  next_sequence: number | null;
}

// ---- Artifact ----
export interface Artifact {
  id: string;
  run_id: string;
  step_id: string | null;
  created_by_agent_id: string | null;
  type: string;
  name: string;
  mime_type: string | null;
  content: string | null;
  storage_url: string | null;
  size_bytes: number | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}