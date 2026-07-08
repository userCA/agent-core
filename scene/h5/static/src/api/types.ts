/* ------------------------------------------------------------------ */
/* SSE v1 event types — api-event-spec-v1                             */
/* ------------------------------------------------------------------ */

// ---- Content Block --------------------------------------------------

export type ContentBlockType =
  | 'text'
  | 'thinking'
  | 'image'
  | 'audio'
  | 'video'
  | 'file'
  | 'component';

export type ContentPhase = 'start' | 'delta' | 'done';

export interface ContentBlock {
  type: ContentBlockType;
  contentId: string;
  index: number;
  phase: ContentPhase;
  content: string;
  meta?: Record<string, any>;
}

// ---- Message lifecycle -----------------------------------------------

export interface MessageStart {
  type: 'message.start';
  messageId: string;
  sessionId: string;
  runId: string;
  createdAt: number;
}

export interface MessageEnd {
  type: 'message.end';
  messageId: string;
  stopReason: StopReason;
  completedAt: number;
  usage: Usage | null;
}

export interface MessageError {
  type: 'message.error';
  messageId: string;
  error: ErrorDetail;
}

export type StopReason =
  | 'end_turn'
  | 'tool_use'
  | 'max_tokens'
  | 'cancelled'
  | 'error';

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
}

export interface ErrorDetail {
  type: string;
  code: string;
  retryable: boolean;
  message?: string;
}

// ---- Action events ---------------------------------------------------

export interface ActionEvent {
  actionType: string;
  toolCallId?: string;
  name?: string;
  arguments?: Record<string, unknown>;
  output?: string;
  result?: ToolResult;
  prompt?: string;
  inputSchema?: JsonInputSchema;
  timeoutSeconds?: number;
  stepId?: string;
  stepName?: string;
  [key: string]: any;
}

export interface ToolResult {
  output: string;
  isError: boolean;
  display?: DisplayPayload;
}

// ---- State events ----------------------------------------------------

export interface StateSnapshot {
  type: 'state.snapshot';
  snapshot: Record<string, any>;
}

export interface StateDelta {
  type: 'state.delta';
  delta: Record<string, any>;
}

// ---- Heart -----------------------------------------------------------

export interface HeartEvent {
  type: 'heart';
}

// ---- Companion -------------------------------------------------------

export interface CompanionState {
  companionType: 'state';
  uid: string;
  emotion: string;
  eyeOverride: string | null;
  frontendMood: string;
}

export interface CompanionBubble {
  companionType: 'bubble';
  uid: string;
  text: string;
  ttlMs: number;
  priority: string;
}

// ---- InputSchema (JSON Schema format) --------------------------------

export type JsonInputSchema = {
  type: 'object';
  properties: Record<string, any>;
  required?: string[];
};

// ---- Display payloads (used in tool_call.completed result.display) ---

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

// ---- REST API types --------------------------------------------------

export interface SessionMeta {
  session_id: string;
  created_at: string;
  entry_count: number;
  title?: string;
}

// ---- Union -----------------------------------------------------------

export type SSEEvent =
  | MessageStart
  | MessageEnd
  | MessageError
  | ContentBlock
  | ActionEvent
  | StateSnapshot
  | StateDelta
  | HeartEvent
  | CompanionState
  | CompanionBubble;
