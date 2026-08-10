/* ------------------------------------------------------------------ */
/* SSE event types — match backend events.py                         */
/* ------------------------------------------------------------------ */

export interface SessionIdEvent {
  event: 'session_id';
  session_id: string;
}

export interface SessionMeta {
  session_id: string;
  created_at: string;
  entry_count: number;
  title?: string;
}

export interface ThinkingDeltaEvent {
  event: 'thinking_delta';
  text: string;
}

export interface TextDeltaEvent {
  event: 'text_delta';
  text: string;
}

export interface ToolStartEvent {
  event: 'tool_start';
  tool_name: string;
  tool_call_id: string;
  args: Record<string, unknown>;
}

export interface ToolUpdateEvent {
  event: 'tool_update';
  tool_name: string;
  result: string;
}

export interface ToolEndEvent {
  event: 'tool_end';
  tool_name: string;
  tool_call_id: string;
  result: string;
  is_error: boolean;
  display?: DisplayPayload;
}

export interface DelegationEvent {
  event: 'delegation';
  phase: 'start' | 'agent_start' | 'agent_end' | 'end';
  mode?: 'single' | 'parallel' | 'chain';
  delegation_id?: string;
  agent?: string;
  task?: string;
  status?: 'running' | 'completed' | 'failed' | 'aborted';
  index?: number;
  total?: number;
  summary?: string;
  error_message?: string | null;
  session_id?: string;
}

export interface PlanStepPayload {
  id: string;
  title: string;
  status: string;
  detail?: string | null;
}

export interface PlanPayload {
  id: string;
  title: string;
  status: string;
  steps: PlanStepPayload[];
  version: number;
}

export interface PlanEvent {
  event: 'plan';
  phase: string;
  plan?: PlanPayload | null;
  done?: number;
  total?: number;
  version?: number;
  owner?: string;
  session_id?: string;
  updated_at?: string;
  error_message?: string | null;
}

export interface WorkflowEvent {
  event: 'workflow';
  run_id?: string;
  name?: string;
  status?: 'running' | 'completed' | 'failed' | 'aborted' | 'paused';
  phase?: string | null;
  phases?: string[];
  log?: string[];
  progress?: { completed_agents?: number; total_agents?: number };
  error_message?: string | null;
  result?: unknown;
}

export interface DisplayPayload {
  widget?: WidgetDisplay;
  audio?: AudioDisplay;
  video?: VideoDisplay;
}

export interface VideoDisplay {
  url: string;
  size?: string;
  seconds?: string;
}

export interface WidgetDisplay {
  version: number;
  html: string;
  title?: string;
  height?: number;
}

export interface AudioDisplay {
  urls: string[];
  task_id?: string;
  prompt?: string;
}

export interface HumanInputRequiredEvent {
  event: 'human_input_required';
  tool_call_id: string;
  prompt: string;
  input_schema: InputSchema;
}

export interface InputSchema {
  fields: InputField[];
}

export interface InputField {
  type: 'text' | 'textarea' | 'select' | 'image_upload' | 'audio_record';
  name: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  options?: SelectOption[];
  max?: number;
  accept?: string;
}

export interface SelectOption {
  label: string;
  value: string;
  preview_url?: string;
}

export interface MessageEndEvent {
  event: 'message_end';
  usage: UsageInfo | null;
}

export interface UsageInfo {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export interface ErrorEvent {
  event: 'error';
  message: string;
}

export interface DoneEvent {
  event: 'done';
}

// Companion events from backend EmotionFSM
export interface CompanionEvent {
  event: 'companion';
  type: string;
  uid: string;
  emotion: string;
  eye_override: string | null;
  frontend_mood: string;
}
export interface CompanionBubbleEvent {
  event: 'companion_bubble';
  uid: string;
  text: string;
  ttl_ms: number;
  priority: string;
}

export type SSEEvent =
  | SessionIdEvent
  | ThinkingDeltaEvent
  | TextDeltaEvent
  | ToolStartEvent
  | ToolUpdateEvent
  | ToolEndEvent
  | DelegationEvent
  | PlanEvent
  | WorkflowEvent
  | HumanInputRequiredEvent
  | MessageEndEvent
  | ErrorEvent
  | DoneEvent
  | CompanionEvent
  | CompanionBubbleEvent;
