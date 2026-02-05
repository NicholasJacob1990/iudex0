'use client';

import React, { useRef } from 'react';
import { useTheme } from 'next-themes';
import { useVorbiumPaint } from '@/hooks/use-vorbium-paint';

type WorkletName = 'verbium-particles' | 'nebula-flow' | 'grid-pulse' | 'wave-field';

interface PaintBackgroundProps {
    worklet: WorkletName;
    /** Theme color override (hex). Defaults to indigo based on theme. */
    color?: string;
    /** Seed for deterministic randomness. Default varies by worklet. */
    seed?: number;
    /** Additional CSS class for the container */
    className?: string;
    /** Extra inline style overrides for worklet custom properties */
    style?: React.CSSProperties;
}

const WORKLET_DEFAULTS: Record<WorkletName, { seed: number }> = {
    'verbium-particles': { seed: 42 },
    'nebula-flow': { seed: 77 },
    'grid-pulse': { seed: 33 },
    'wave-field': { seed: 55 },
};

/**
 * Renders a CSS Houdini Paint Worklet as an absolute-positioned background layer.
 * Falls back to Canvas 2D on browsers without paint worklet support (Safari/Firefox).
 */
export function PaintBackground({ worklet, color, seed, className, style }: PaintBackgroundProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const { theme, systemTheme } = useTheme();

    const currentTheme = theme === 'system' ? systemTheme : theme;
    const isDark = currentTheme === 'dark';
    const themeColor = color ?? (isDark ? '#6366f1' : '#4f46e5');
    const seedValue = seed ?? WORKLET_DEFAULTS[worklet].seed;

    const { hasPaintWorklet } = useVorbiumPaint(containerRef, worklet, {
        seed: seedValue,
        color: themeColor,
    });

    // Only apply paint() CSS when worklets are supported (Chrome/Edge).
    // Safari/Firefox get a <canvas> fallback injected by the hook.
    const baseStyle: React.CSSProperties = hasPaintWorklet ? {
        '--cursor-x': '0.5',
        '--cursor-y': '0.5',
        '--theme-color': themeColor,
        '--seed': String(seedValue),
        '--animation-tick': '0',
        '--t': '0',
        animation: 'ripple 6s linear infinite, vorbiumTime 60s linear infinite',
        backgroundImage: `paint(${worklet})`,
        ...style,
    } as React.CSSProperties : {
        '--theme-color': themeColor,
        ...style,
    } as React.CSSProperties;

    return (
        <div
            ref={containerRef}
            className={`absolute inset-0 pointer-events-none ${className ?? ''}`}
            style={baseStyle}
            aria-hidden="true"
        />
    );
}
