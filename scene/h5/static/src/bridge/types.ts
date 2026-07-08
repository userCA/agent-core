export interface PushPayload {
  title?: string;
  body: string;
  data?: Record<string, string>;
}

export interface ImagePickerOptions {
  maxFiles?: number;
  accept?: string;
}

export interface ImageResult {
  files: { base64: string; mimeType: string; fileName: string }[];
}

export interface AudioResult {
  base64: string;
  mimeType: string;
  durationMs: number;
}

/**
 * Abstraction over browser vs. native app runtime.
 * In browser: localStorage + Web APIs.
 * In app: JSBridge calls to native layer.
 */
export interface NativeBridge {
  readonly platform: 'ios' | 'android' | 'web';

  // Storage
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;

  // Push notifications (app only)
  registerPush?(callback: (payload: PushPayload) => void): Promise<string>;

  // Native media (app only — falls back to Web APIs otherwise)
  chooseImage?(options: ImagePickerOptions): Promise<ImageResult>;
  startRecord?(): Promise<void>;
  stopRecord?(): Promise<AudioResult>;

  // App lifecycle
  onAppForeground(cb: () => void): () => void;
  onAppBackground(cb: () => void): () => void;
}
