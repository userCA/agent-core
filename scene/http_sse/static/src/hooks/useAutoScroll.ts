import { useRef, useCallback, useEffect } from 'react';

const NEAR_BOTTOM_THRESHOLD = 80; // px from bottom to trigger auto-scroll

export function useAutoScroll(deps: unknown[]) {
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolling = useRef(false);
  const scrollTimeout = useRef<ReturnType<typeof setTimeout>>();
  const scrollRaf = useRef<number>();
  const debounceTimer = useRef<ReturnType<typeof setTimeout>>();

  const isNearBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight <= NEAR_BOTTOM_THRESHOLD;
  }, []);

  const onScroll = useCallback(() => {
    userScrolling.current = true;
    if (scrollTimeout.current) clearTimeout(scrollTimeout.current);
    scrollTimeout.current = setTimeout(() => {
      userScrolling.current = false;
    }, 1500);
  }, []);

  const scrollToBottom = useCallback((smooth = false) => {
    if (userScrolling.current) return;
    // Only auto-scroll if user is already near the bottom
    if (!isNearBottom()) return;

    if (scrollRaf.current) cancelAnimationFrame(scrollRaf.current);
    scrollRaf.current = requestAnimationFrame(() => {
      const el = containerRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
    });
  }, [isNearBottom]);

  // Debounced auto-scroll: coalesce rapid dep changes into a single scroll
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    debounceTimer.current = setTimeout(() => {
      scrollToBottom(false);
    }, 40);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
      if (scrollTimeout.current) clearTimeout(scrollTimeout.current);
      if (scrollRaf.current) cancelAnimationFrame(scrollRaf.current);
    };
  }, []);

  return { containerRef, onScroll, scrollToBottom };
}
