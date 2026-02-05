import { useState, useEffect, useMemo, useCallback, type RefObject } from 'react';

interface FullscreenRefs {
  chat: RefObject<HTMLElement | null>;
  canvas: RefObject<HTMLElement | null>;
  root: RefObject<HTMLElement | null>;
}

export function useFullscreen() {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pendingTarget, setPendingTarget] = useState<'chat' | 'canvas' | 'split' | null>(null);

  const supported = useMemo(() => {
    if (typeof document === 'undefined') return false;
    return typeof document.documentElement?.requestFullscreen === 'function';
  }, []);

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    onChange();
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  const enterFullscreen = useCallback(async (target?: HTMLElement | null) => {
    if (!supported) return;
    try {
      const el = target || document.documentElement;
      await el.requestFullscreen?.();
    } catch {
      // ignore
    }
  }, [supported]);

  const exitFullscreen = useCallback(async () => {
    if (typeof document === 'undefined') return;
    if (!document.fullscreenElement) return;
    try {
      await document.exitFullscreen();
    } catch {
      // ignore
    }
  }, []);

  const toggleFullscreen = useCallback(
    (layoutMode: string, refs: FullscreenRefs) => {
      if (!supported) return;
      if (isFullscreen) {
        void exitFullscreen();
        return;
      }
      if (layoutMode === 'chat') {
        setPendingTarget('chat');
      } else if (layoutMode === 'canvas') {
        setPendingTarget('canvas');
      } else {
        setPendingTarget('split');
      }
    },
    [supported, isFullscreen, exitFullscreen],
  );

  const applyPendingFullscreen = useCallback(
    (layoutMode: string, refs: FullscreenRefs) => {
      if (!pendingTarget) return;
      if (typeof document === 'undefined') return;

      void (async () => {
        let targetEl: HTMLElement | null = null;
        if (pendingTarget === 'chat') {
          targetEl = refs.chat.current;
        } else if (pendingTarget === 'canvas') {
          targetEl = refs.canvas.current;
        } else {
          targetEl = refs.root.current;
        }
        await enterFullscreen(targetEl);
        setPendingTarget(null);
      })();
    },
    [pendingTarget, enterFullscreen],
  );

  return {
    isFullscreen,
    supported,
    pendingTarget,
    setPendingTarget,
    enterFullscreen,
    exitFullscreen,
    toggleFullscreen,
    applyPendingFullscreen,
  };
}
