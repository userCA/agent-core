import type { NativeBridge, PushPayload, ImagePickerOptions, ImageResult, AudioResult } from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */
type AnyWindow = Record<string, any>;

function getBridge<T>(key: string): T | undefined {
  return (window as unknown as AnyWindow)[key] as T | undefined;
}

/**
 * App webview JSBridge implementation.
 * Calls window.JSBridge.call(method, params) — the standard pattern
 * used by most Chinese app webview containers.
 */
export function createNativeBridge(): NativeBridge {
  const platform = detectPlatform();

  function callNative<T>(method: string, params?: unknown): Promise<T> {
    return new Promise((resolve, reject) => {
      try {
        const bridge = getBridge<{ call: (m: string, p: unknown, cb: (err: unknown, result: T) => void) => void }>('JSBridge');
        if (!bridge) {
          reject(new Error('JSBridge not available'));
          return;
        }
        bridge.call(method, params || {}, (err, result) => {
          if (err) reject(err);
          else resolve(result);
        });
      } catch (e) {
        reject(e);
      }
    });
  }

  return {
    platform,

    async getItem(key) {
      try {
        return await callNative<string | null>('storage.get', { key });
      } catch {
        return localStorage.getItem(key);
      }
    },
    async setItem(key, value) {
      try {
        await callNative('storage.set', { key, value });
      } catch {
        localStorage.setItem(key, value);
      }
    },
    async removeItem(key) {
      try {
        await callNative('storage.remove', { key });
      } catch {
        localStorage.removeItem(key);
      }
    },

    async registerPush(callback) {
      const bridge = getBridge<{ on: (event: string, cb: (payload: PushPayload) => void) => void }>('JSBridge');
      if (bridge) {
        bridge.on('push', callback);
      }
      return callNative<string>('push.register', {});
    },

    async chooseImage(options) {
      return callNative<ImageResult>('media.chooseImage', options);
    },

    async startRecord() {
      await callNative('media.startRecord');
    },
    async stopRecord() {
      return callNative<AudioResult>('media.stopRecord');
    },

    onAppForeground(cb) {
      const bridge = getBridge<{ on: (e: string, cb: () => void) => void; off: (e: string, cb: () => void) => void }>('JSBridge');
      if (bridge) {
        bridge.on('foreground', cb);
        return () => bridge.off('foreground', cb);
      }
      const handler = () => { if (document.visibilityState === 'visible') cb(); };
      document.addEventListener('visibilitychange', handler);
      return () => document.removeEventListener('visibilitychange', handler);
    },

    onAppBackground(cb) {
      const bridge = getBridge<{ on: (e: string, cb: () => void) => void; off: (e: string, cb: () => void) => void }>('JSBridge');
      if (bridge) {
        bridge.on('background', cb);
        return () => bridge.off('background', cb);
      }
      const handler = () => { if (document.visibilityState === 'hidden') cb(); };
      document.addEventListener('visibilitychange', handler);
      return () => document.removeEventListener('visibilitychange', handler);
    },
  };
}

function detectPlatform(): 'ios' | 'android' | 'web' {
  const ua = navigator.userAgent.toLowerCase();
  if (/iphone|ipad|ipod/.test(ua)) return 'ios';
  if (/android/.test(ua)) return 'android';
  return 'web';
}
