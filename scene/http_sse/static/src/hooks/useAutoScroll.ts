import { useRef, useCallback, useEffect, useState } from 'react';

const NEAR_BOTTOM_THRESHOLD = 80;
const SHOW_BUTTON_DISTANCE = 200;

export function useAutoScroll(deps: unknown[]) {
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolling = useRef(false);
  const scrollTimeout = useRef<ReturnType<typeof setTimeout>>();
  const scrollRaf = useRef<number>();
  const debounceTimer = useRef<ReturnType<typeof setTimeout>>();
  const [showButton, setShowButton] = useState(false);

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
    // Show button when scrolled > 200px from bottom
    const el = containerRef.current;
    if (el) {
      setShowButton(el.scrollHeight - el.scrollTop - el.clientHeight > SHOW_BUTTON_DISTANCE);
    }
  }, []);

  const scrollToBottom = useCallback((smooth = false) => {
    if (userScrolling.current && !smooth) return;
    if (!smooth && !isNearBottom()) return;

    if (scrollRaf.current) cancelAnimationFrame(scrollRaf.current);
    scrollRaf.current = requestAnimationFrame(() => {
      const el = containerRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
      setShowButton(false);
    });
  }, [isNearBottom]);

  const forceScrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    setShowButton(false);
  }, []);

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

  return { containerRef, onScroll, scrollToBottom, showButton, forceScrollToBottom };
}
