'use client';

import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { useCanvasStore } from '@/stores';

/**
 * Manages split-panel resize, fullscreen toggle, and layout mode derivation.
 */
export function useLayoutResize() {
  const {
    state: canvasState,
    showCanvas,
    hideCanvas,
    setState: setCanvasState,
    setActiveTab,
  } = useCanvasStore();

  // ------ Local state ------
  const [chatPanelWidth, setChatPanelWidth] = useState(50);
  const [isResizing, setIsResizing] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [pendingFullscreenTarget, setPendingFullscreenTarget] = useState<
    'chat' | 'canvas' | 'split' | null
  >(null);

  // ------ Refs ------
  const pageRootRef = useRef<HTMLDivElement>(null);
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const chatPanelRef = useRef<HTMLDivElement>(null);
  const canvasPanelRef = useRef<HTMLDivElement>(null);
  const dragRectRef = useRef<DOMRect | null>(null);
  const rafRef = useRef<number | null>(null);

  // ------ Derived ------
  const layoutMode: 'chat' | 'split' | 'canvas' =
    canvasState === 'hidden' ? 'chat' : canvasState === 'expanded' ? 'canvas' : 'split';
  const chatActive = layoutMode !== 'canvas';
  const canvasActive = layoutMode !== 'chat';

  // ------ Fullscreen API ------
  const fullscreenApi = useMemo(() => {
    if (typeof document === 'undefined') return { supported: false as const };
    return {
      supported: typeof document.documentElement?.requestFullscreen === 'function',
    };
  }, []);

  const enterFullscreen = async (target?: HTMLElement | null) => {
    if (!fullscreenApi.supported) return;
    try {
      const el = target || pageRootRef.current || document.documentElement;
      // @ts-ignore
      await el.requestFullscreen?.();
    } catch {
      // ignore
    }
  };

  const exitFullscreen = async () => {
    if (typeof document === 'undefined') return;
    if (!document.fullscreenElement) return;
    try {
      await document.exitFullscreen();
    } catch {
      // ignore
    }
  };

  // ------ Effects ------

  // Track browser fullscreen state
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const onChange = () => setIsFullscreen(!!document.fullscreenElement);
    onChange();
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  // Handle resize cursor
  useEffect(() => {
    if (!isResizing) return;
    const { style } = document.body;
    const prevCursor = style.cursor;
    const prevUserSelect = style.userSelect;
    style.cursor = 'col-resize';
    style.userSelect = 'none';
    return () => {
      style.cursor = prevCursor;
      style.userSelect = prevUserSelect;
    };
  }, [isResizing]);

  // Clamp width on window resize (min 300px, max 70%)
  useEffect(() => {
    const container = splitContainerRef.current;
    if (!container) return;

    const handleResize = () => {
      const rect = container.getBoundingClientRect();
      if (!rect.width) return;
      const minPx = 300;
      const maxPx = Math.max(minPx, rect.width * 0.7);
      const currentPx = (chatPanelWidth / 100) * rect.width;
      if (currentPx < minPx) {
        setChatPanelWidth((minPx / rect.width) * 100);
      } else if (currentPx > maxPx) {
        setChatPanelWidth((maxPx / rect.width) * 100);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [chatPanelWidth]);

  // RAF-throttled pointer move
  const updateChatWidthFromPointer = useCallback((clientX: number) => {
    const rect = dragRectRef.current;
    if (!rect || !rect.width) return;

    const minPx = 300;
    const maxPx = Math.max(minPx, rect.width * 0.7);
    const rawPx = clientX - rect.left;
    const clampedPx = Math.min(Math.max(rawPx, minPx), maxPx);
    setChatPanelWidth((clampedPx / rect.width) * 100);
  }, []);

  // Global pointer listeners for resize
  useEffect(() => {
    if (!isResizing) return;

    const handlePointerMove = (event: PointerEvent) => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = requestAnimationFrame(() => {
        updateChatWidthFromPointer(event.clientX);
      });
    };

    const handlePointerUp = () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      dragRectRef.current = null;
      setIsResizing(false);
    };

    window.addEventListener('pointermove', handlePointerMove);
    window.addEventListener('pointerup', handlePointerUp);
    window.addEventListener('pointercancel', handlePointerUp);
    window.addEventListener('blur', handlePointerUp);

    return () => {
      window.removeEventListener('pointermove', handlePointerMove);
      window.removeEventListener('pointerup', handlePointerUp);
      window.removeEventListener('pointercancel', handlePointerUp);
      window.removeEventListener('blur', handlePointerUp);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isResizing, updateChatWidthFromPointer]);

  // Handle pending fullscreen target
  useEffect(() => {
    if (!pendingFullscreenTarget) return;
    if (typeof document === 'undefined') return;

    void (async () => {
      let targetEl: HTMLElement | null = null;
      if (pendingFullscreenTarget === 'chat') {
        targetEl = chatPanelRef.current;
      } else if (pendingFullscreenTarget === 'canvas') {
        targetEl = canvasPanelRef.current;
      } else {
        targetEl = pageRootRef.current;
      }
      await enterFullscreen(targetEl);
      setPendingFullscreenTarget(null);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingFullscreenTarget, layoutMode]);

  // ------ Handlers ------

  const handleToggleFullscreen = () => {
    if (!fullscreenApi.supported) return;
    if (isFullscreen) {
      void exitFullscreen();
      return;
    }
    if (layoutMode === 'chat') {
      setPendingFullscreenTarget('chat');
      return;
    }
    if (layoutMode === 'canvas') {
      setPendingFullscreenTarget('canvas');
      return;
    }
    setPendingFullscreenTarget('split');
  };

  const toggleChatMode = () => {
    if (layoutMode === 'chat') {
      showCanvas();
      setCanvasState('normal');
      return;
    }
    hideCanvas();
  };

  const toggleCanvasMode = () => {
    if (layoutMode === 'canvas') {
      showCanvas();
      setCanvasState('normal');
      return;
    }
    showCanvas();
    setCanvasState('expanded');
  };

  const handleDividerPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (canvasState !== 'normal') return;
    event.preventDefault();

    const container = splitContainerRef.current;
    if (container) {
      dragRectRef.current = container.getBoundingClientRect();
    }

    setIsResizing(true);
  };

  return {
    // Canvas store pass-through
    canvasState,
    showCanvas,
    hideCanvas,
    setCanvasState,
    setActiveTab,

    // Layout state
    chatPanelWidth,
    setChatPanelWidth,
    isResizing,
    isFullscreen,

    // Derived
    layoutMode,
    chatActive,
    canvasActive,

    // Refs
    pageRootRef,
    splitContainerRef,
    chatPanelRef,
    canvasPanelRef,

    // Fullscreen
    fullscreenApi,
    enterFullscreen,
    exitFullscreen,

    // Extra state (read-only for consumers)
    pendingFullscreenTarget,

    // Handlers
    handleToggleFullscreen,
    toggleChatMode,
    toggleCanvasMode,
    handleDividerPointerDown,
    updateChatWidthFromPointer,
  };
}
