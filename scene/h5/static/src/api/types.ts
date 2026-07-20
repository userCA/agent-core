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
// tool_call.started:    { actionType, toolCallId, name, arguments }
// tool_call.completed:  { actionType, toolCallId, result }
// tool_call.progress:   { actionType, toolCallId, output }
// skill.started:        { actionType, skillId, skillName }
// skill.completed:      { actionType, skillId }
// step.start / step.end { actionType, stepId, stepName, type? }
// human_input.*:        { actionType, toolCallId, prompt, inputSchema }
// delegation.update:    { actionType, delegation_id, phase, mode, agent, ... }
// plan.update:          { actionType, phase, plan, done, total, ... }

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
  // delegation.update fields (snake_case from backend details)
  delegation_id?: string;
  phase?: string;
  mode?: string;
  agent?: string;
  status?: string;
  task?: string;
  summary?: string;
  // plan.update fields
  plan?: {
    id: string;
    title: string;
    status: string;
    steps: Array<{ id: string; title: string; status: string; detail?: string | null }>;
    version: number;
  } | null;
  done?: number;
  total?: number;
  version?: number;
  error_message?: string | null;
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
  image?: ImageDisplay | ImageDisplay[];
}

export interface ImageDisplay {
  url: string;
  size?: string;
  width?: number;
  height?: number;
  format?: string;
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

// ---- Chat request content blocks (spec §9.1) -------------------------

export interface ContentBlockInput {
  type: 'text' | 'image' | 'audio' | 'video' | 'file';
  content: string;
  meta?: Record<string, any>;
}

export interface ChatRequest {
  message: string;
  content?: ContentBlockInput[];
  provider?: string | null;
  model?: string | null;
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
