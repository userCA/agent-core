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

export type SSEEvent =
  | SessionIdEvent
  | ThinkingDeltaEvent
  | TextDeltaEvent
  | ToolStartEvent
  | ToolUpdateEvent
  | ToolEndEvent
  | HumanInputRequiredEvent
  | MessageEndEvent
  | ErrorEvent
  | DoneEvent;
