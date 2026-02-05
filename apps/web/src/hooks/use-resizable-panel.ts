import { useState, useEffect, useRef, useCallback } from 'react';

interface UseResizablePanelOptions {
  initialWidth?: number;
  minPx?: number;
  maxPercent?: number;
  enabled?: boolean;
}

export function useResizablePanel({
  initialWidth = 50,
  minPx = 300,
  maxPercent = 70,
  enabled = true,
}: UseResizablePanelOptions = {}) {
  const [chatPanelWidth, setChatPanelWidth] = useState(initialWidth);
  const [isResizing, setIsResizing] = useState(false);
  const splitContainerRef = useRef<HTMLDivElement>(null);
  const dragRectRef = useRef<DOMRect | null>(null);
  const rafRef = useRef<number | null>(null);

  // Handle resize cursor state
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

  // Clamp width on window resize
  useEffect(() => {
    const container = splitContainerRef.current;
    if (!container) return;

    const handleResize = () => {
      const rect = container.getBoundingClientRect();
      if (!rect.width) return;
      const maxPx = Math.max(minPx, rect.width * (maxPercent / 100));
      const currentPx = (chatPanelWidth / 100) * rect.width;
      if (currentPx < minPx) {
        setChatPanelWidth((minPx / rect.width) * 100);
      } else if (currentPx > maxPx) {
        setChatPanelWidth((maxPx / rect.width) * 100);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [chatPanelWidth, minPx, maxPercent]);

  const updateChatWidthFromPointer = useCallback(
    (clientX: number) => {
      const rect = dragRectRef.current;
      if (!rect || !rect.width) return;
      const maxPx = Math.max(minPx, rect.width * (maxPercent / 100));
      const rawPx = clientX - rect.left;
      const clampedPx = Math.min(Math.max(rawPx, minPx), maxPx);
      setChatPanelWidth((clampedPx / rect.width) * 100);
    },
    [minPx, maxPercent],
  );

  const handleDividerPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!enabled) return;
      event.preventDefault();
      const container = splitContainerRef.current;
      if (container) {
        dragRectRef.current = container.getBoundingClientRect();
      }
      setIsResizing(true);
    },
    [enabled],
  );

  // Global listeners for resize (more robust than element listeners)
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

  const dividerKeyDown = useCallback((e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 5 : 1;
    if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setChatPanelWidth((w) => Math.max(20, w - step));
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      setChatPanelWidth((w) => Math.min(70, w + step));
    }
  }, []);

  return {
    chatPanelWidth,
    setChatPanelWidth,
    isResizing,
    splitContainerRef,
    handleDividerPointerDown,
    dividerKeyDown,
  };
}
