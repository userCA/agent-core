import type { NativeBridge } from './types';

const noop = () => () => {};

/**
 * Browser fallback that uses localStorage and Web APIs.
 * Preserves the exact same behavior as the legacy vanilla JS frontend.
 */
export function createWebBridge(): NativeBridge {
  return {
    platform: 'web',

    async getItem(key) {
      return localStorage.getItem(key);
    },
    async setItem(key, value) {
      localStorage.setItem(key, value);
    },
    async removeItem(key) {
      localStorage.removeItem(key);
    },

    onAppForeground: noop,
    onAppBackground: noop,
  };
}
