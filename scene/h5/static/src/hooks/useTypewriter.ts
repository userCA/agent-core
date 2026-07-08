import { useRef, useCallback, useEffect, useMemo } from 'react';

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
 * - requestAnimationFrame-based loop prevents setTimeout backlog and adapts speed
 *   when the stream outpaces the display, keeping visible lag bounded.
 */
export function useTypewriter(opts: TypewriterOptions = {}) {
  const { speed = 45, onFlush } = opts;
  const queueRef = useRef<string[]>([]);
  const rafRef = useRef<number | null>(null);
  const fullTextRef = useRef('');
  const activeRef = useRef(false);
  const flushScheduled = useRef(false);
  const lastFlushLen = useRef(0);
  const lastTickRef = useRef<number | null>(null);
  const reducedMotionRef = useRef(
    typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );

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

  const tick = useCallback((now: number) => {
    if (queueRef.current.length === 0) {
      activeRef.current = false;
      lastTickRef.current = null;
      scheduleFlush();
      return;
    }
    // Respect prefers-reduced-motion: emit all queued chars immediately
    if (reducedMotionRef.current) {
      fullTextRef.current += queueRef.current.join('');
      queueRef.current = [];
      scheduleFlush();
      activeRef.current = false;
      lastTickRef.current = null;
      return;
    }
    if (lastTickRef.current === null) lastTickRef.current = now;
    const elapsed = now - lastTickRef.current;
    lastTickRef.current = now;

    const backlog = queueRef.current.length;
    // Slow near the end for the classic typewriter feel; speed up when the
    // stream is outpacing the display so the visible lag stays bounded.
    let adjustedSpeed = speed;
    if (backlog <= 2) {
      adjustedSpeed = speed * 2.5;
    } else if (backlog > 120) {
      adjustedSpeed = speed * 0.25;
    } else if (backlog > 60) {
      adjustedSpeed = speed * 0.5;
    } else if (backlog > 20) {
      adjustedSpeed = speed * 0.75;
    }

    const charsToEmit = Math.max(1, Math.floor(elapsed / adjustedSpeed));
    const emit = Math.min(charsToEmit, backlog);
    fullTextRef.current += queueRef.current.splice(0, emit).join('');
    scheduleFlush();
    rafRef.current = requestAnimationFrame(tick);
  }, [speed, scheduleFlush]);

  const enqueue = useCallback((text: string) => {
    const chars = [...text];
    queueRef.current.push(...chars);
    if (!activeRef.current) {
      activeRef.current = true;
      lastTickRef.current = null;
      rafRef.current = requestAnimationFrame(tick);
    }
  }, [tick]);

  const reset = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    queueRef.current = [];
    fullTextRef.current = '';
    lastFlushLen.current = 0;
    activeRef.current = false;
    flushScheduled.current = false;
    lastTickRef.current = null;
  }, []);

  useEffect(() => {
    const mql = window.matchMedia('(prefers-reduced-motion: reduce)');
    const handler = (e: MediaQueryListEvent) => {
      reducedMotionRef.current = e.matches;
    };
    mql.addEventListener('change', handler);
    return () => {
      mql.removeEventListener('change', handler);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return useMemo(
    () => ({ enqueue, reset, fullTextRef, isActive: activeRef }),
    [enqueue, reset]
  );
}
