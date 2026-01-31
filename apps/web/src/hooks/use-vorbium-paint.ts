'use client';

import { useEffect } from "react";

// Singleton state to track if module is loaded
let loaded = false;

// Cache-bust version — increment to force browser to reload worklet
const WORKLET_VERSION = 9;

async function loadVorbiumWorklet() {
    if (typeof window === 'undefined') return;
    // @ts-ignore - CSS type definition might be missing paintWorklet
    const CSSAny = (window.CSS as any);

    if (!CSSAny?.paintWorklet?.addModule) return;
    if (loaded) return;

    try {
        await CSSAny.paintWorklet.addModule(`/worklets/verbium-particles.js?v=${WORKLET_VERSION}`);
        loaded = true;
    } catch (err) {
        console.warn("Failed to load paint worklet:", err);
    }
}

export function useVorbiumPaint(ref: React.RefObject<HTMLElement>) {
    useEffect(() => {
        // 1. Load the worklet globally (once)
        loadVorbiumWorklet();

        const el = ref.current;
        if (!el) return;

        // 2. Setup interaction logic
        let raf = 0;
        // Start at center
        let lastX = 0.5, lastY = 0.5;

        const update = () => {
            raf = 0;
            el.style.setProperty("--cursor-x", String(lastX));
            el.style.setProperty("--cursor-y", String(lastY));
        };

        const onMove = (ev: PointerEvent) => {
            const rect = el.getBoundingClientRect();
            const x = (ev.clientX - rect.left) / rect.width;
            const y = (ev.clientY - rect.top) / rect.height;

            // Clamp to 0..1 to correspond with worklet logic
            lastX = Math.max(0, Math.min(1, x));
            lastY = Math.max(0, Math.min(1, y));

            if (!raf) raf = requestAnimationFrame(update);
        };

        const onLeave = () => {
            // Reset to center on leave
            lastX = 0.5; lastY = 0.5;
            if (!raf) raf = requestAnimationFrame(update);
        };

        el.addEventListener("pointermove", onMove, { passive: true });
        el.addEventListener("pointerleave", onLeave);

        return () => {
            el.removeEventListener("pointermove", onMove);
            el.removeEventListener("pointerleave", onLeave);
            if (raf) cancelAnimationFrame(raf);
        };
    }, [ref]);
}
