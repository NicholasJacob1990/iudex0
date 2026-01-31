'use client';

import { useEffect, useState, useCallback, type RefObject } from 'react';

export function useScrollProgress(containerRef?: RefObject<HTMLElement | null>) {
  const [progress, setProgress] = useState(0);

  const onScroll = useCallback(() => {
    const el = containerRef?.current ?? document.documentElement;
    const scrollTop = containerRef?.current ? el.scrollTop : window.scrollY;
    const scrollHeight = el.scrollHeight - el.clientHeight;
    setProgress(scrollHeight > 0 ? scrollTop / scrollHeight : 0);
  }, [containerRef]);

  useEffect(() => {
    const target = containerRef?.current ?? window;
    target.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
    return () => target.removeEventListener('scroll', onScroll as EventListener);
  }, [containerRef, onScroll]);

  return progress;
}
