'use client';

import { useEffect, type RefObject } from 'react';

export function useTilt(ref: RefObject<HTMLElement | null>, maxDeg = 8) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onMove = (e: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      const x = (e.clientX - rect.left) / rect.width - 0.5;
      const y = (e.clientY - rect.top) / rect.height - 0.5;
      el.style.transform = `perspective(600px) rotateY(${x * maxDeg}deg) rotateX(${-y * maxDeg}deg)`;
      el.style.transition = 'transform 0.1s ease-out';
    };

    const onLeave = () => {
      el.style.transform = '';
      el.style.transition = 'transform 0.4s ease-out';
    };

    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerleave', onLeave);

    return () => {
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerleave', onLeave);
    };
  }, [ref, maxDeg]);
}
