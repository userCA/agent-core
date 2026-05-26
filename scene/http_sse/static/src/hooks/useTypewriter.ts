import { useRef, useCallback, useEffect } from 'react';

interface TypewriterOptions {
  speed?: number;
  /** Called at ~60fps via rAF. isActive=true while chars are being typed, false when queue pauses. */
  onFlush?: (fullText: string, isActive: boolean) => void;
}

/**
 * Variable-speed typewriter matching legacy behavior:
 * - Fast (speed) when queue > 2 chars, slow (speed × 2.5) when ≤ 2 chars.
 * - All DOM output via onFlush — no textContent writes.
 * - onFlush isActive flag lets callers render raw during typing, markdown on pause.
 */
export function useTypewriter(opts: TypewriterOptions = {}) {
  const { speed = 45, onFlush } = opts;
  const queueRef = useRef<string[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fullTextRef = useRef('');
  const activeRef = useRef(false);
  const flushScheduled = useRef(false);
  const lastFlushLen = useRef(0);

  const doFlush = useCallback(() => {
    flushScheduled.current = false;
    const current = fullTextRef.current;
    if (current.length !== lastFlushLen.current) {
      lastFlushLen.current = current.length;
      onFlush?.(current, activeRef.current);
    }
  }, [onFlush]);

  const scheduleFlush = useCallback(() => {
    if (!flushScheduled.current) {
      flushScheduled.current = true;
      requestAnimationFrame(() => doFlush());
    }
  }, [doFlush]);

  const runLoop = useCallback(() => {
    if (queueRef.current.length === 0) {
      activeRef.current = false;
      scheduleFlush(); // final flush with isActive=false → markdown mode
      return;
    }
    const ch = queueRef.current.shift()!;
    fullTextRef.current += ch;
    scheduleFlush();
    // Variable speed: fast when backlog, slow when near end (matches legacy)
    const delay = queueRef.current.length <= 2 ? speed * 2.5 : speed;
    timerRef.current = setTimeout(runLoop, delay);
  }, [speed, scheduleFlush]);

  const enqueue = useCallback((text: string) => {
    const chars = [...text];
    queueRef.current.push(...chars);
    if (!activeRef.current) {
      activeRef.current = true;
      runLoop();
    }
  }, [runLoop]);

  const reset = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    queueRef.current = [];
    fullTextRef.current = '';
    lastFlushLen.current = 0;
    activeRef.current = false;
    flushScheduled.current = false;
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { enqueue, reset, fullTextRef, isActive: activeRef };
}
