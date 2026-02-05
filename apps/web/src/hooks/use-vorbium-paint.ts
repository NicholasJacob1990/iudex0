'use client';

import { useEffect, useState } from "react";

// ============================================================
// Paint Worklet loader (Chrome/Edge only)
// ============================================================
const loadedWorklets = new Set<string>();
const WORKLET_VERSION = 10;

type WorkletName = 'verbium-particles' | 'nebula-flow' | 'grid-pulse' | 'wave-field';

const WORKLET_FILES: Record<WorkletName, string> = {
    'verbium-particles': '/worklets/verbium-particles.js',
    'nebula-flow': '/worklets/nebula-flow.js',
    'grid-pulse': '/worklets/grid-pulse.js',
    'wave-field': '/worklets/wave-field.js',
};

export function supportsPaintWorklet(): boolean {
    if (typeof window === 'undefined') return false;
    return !!(window.CSS as any)?.paintWorklet?.addModule;
}

async function loadWorklet(name: WorkletName) {
    if (typeof window === 'undefined') return false;
    const CSSAny = (window.CSS as any);
    if (!CSSAny?.paintWorklet?.addModule) return false;
    if (loadedWorklets.has(name)) return true;
    try {
        await CSSAny.paintWorklet.addModule(`${WORKLET_FILES[name]}?v=${WORKLET_VERSION}`);
        loadedWorklets.add(name);
        return true;
    } catch (err) {
        console.warn(`Failed to load paint worklet ${name}:`, err);
        return false;
    }
}

// ============================================================
// Shared utilities
// ============================================================
function mulberry32(a: number) {
    return function () {
        a |= 0;
        a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

function parseHexToRgb(hex: string): [number, number, number] {
    let c = hex.replace('#', '');
    if (c.length === 3) c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
    const n = parseInt(c, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function detectDark(): boolean {
    if (typeof document === 'undefined') return true;
    return document.documentElement.classList.contains('dark') ||
        document.documentElement.getAttribute('data-theme') === 'dark' ||
        (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches);
}

// ============================================================
// Sprite cache (pre-render to offscreen canvas)
// ============================================================
const spriteCache = new Map<string, HTMLCanvasElement>();

function getParticleSprite(r: number, g: number, b: number, alpha: number, size: number): HTMLCanvasElement {
    const qr = (r >> 4) << 4;
    const qg = (g >> 4) << 4;
    const qb = (b >> 4) << 4;
    const qa = Math.round(alpha * 10) / 10;
    const qs = Math.round(size * 2) / 2;
    const key = `${qr},${qg},${qb},${qa},${qs}`;

    let sprite = spriteCache.get(key);
    if (sprite) return sprite;

    const pad = 2;
    const dim = Math.ceil(qs * 2 + pad * 2);
    sprite = document.createElement('canvas');
    sprite.width = dim;
    sprite.height = dim;
    const sx = sprite.getContext('2d')!;
    sx.fillStyle = `rgba(${qr},${qg},${qb},${qa})`;
    sx.beginPath();
    sx.arc(dim / 2, dim / 2, qs, 0, Math.PI * 2);
    sx.fill();

    spriteCache.set(key, sprite);
    return sprite;
}

// ============================================================
// Canvas fallback framework — shared setup for all worklets
// ============================================================
interface FallbackConfig {
    seed: number;
    colorOverride?: string; // hex color override from component
}

type RenderFn = (
    ctx: CanvasRenderingContext2D,
    w: number, h: number,
    cursorX: number, cursorY: number,
    t: number,
    isDark: boolean,
    cr: number, cg: number, cb: number,
    seed: number,
) => void;

function createCanvasFallback(
    container: HTMLElement,
    renderFn: RenderFn,
    config: FallbackConfig,
    drawBackground: boolean,
): () => void {
    const canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;z-index:0;';
    // Ensure container is a positioned context for the canvas child.
    // Don't override if already positioned (absolute/fixed/sticky from Tailwind).
    const pos = getComputedStyle(container).position;
    if (pos === 'static') container.style.position = 'relative';
    container.insertBefore(canvas, container.firstChild);

    const ctxOptions: CanvasRenderingContext2DSettings & {
        desynchronized?: boolean;
        willReadFrequently?: boolean;
    } = { alpha: true, desynchronized: true, willReadFrequently: false };
    const ctx = canvas.getContext('2d', ctxOptions);
    if (!ctx) return () => {};

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';

    // Target cursor (set by events), smoothed cursor (used for rendering).
    // Matches Chrome's CSS: transition: --cursor-x 0.3s cubic-bezier(0.2, 0.8, 0.2, 1)
    let targetX = 0.5, targetY = 0.5;
    let cursorX = 0.5, cursorY = 0.5;
    let running = true;
    const LERP_SPEED = 8; // ~0.3s to reach target at 60fps (1 - (1-8/60)^18 ≈ 0.95)

    const onPointer = (ev: PointerEvent) => {
        const rect = container.getBoundingClientRect();
        targetX = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
        targetY = Math.max(0, Math.min(1, (ev.clientY - rect.top) / rect.height));
    };
    const onTouch = (ev: TouchEvent) => {
        const touch = ev.touches[0];
        if (!touch) return;
        const rect = container.getBoundingClientRect();
        targetX = Math.max(0, Math.min(1, (touch.clientX - rect.left) / rect.width));
        targetY = Math.max(0, Math.min(1, (touch.clientY - rect.top) / rect.height));
    };
    const onLeave = () => { targetX = 0.5; targetY = 0.5; };

    container.addEventListener('pointermove', onPointer, { passive: true });
    container.addEventListener('touchmove', onTouch, { passive: true });
    container.addEventListener('pointerleave', onLeave);

    let isDark = detectDark();
    const getColor = (): [number, number, number] => {
        if (config.colorOverride) return parseHexToRgb(config.colorOverride);
        return parseHexToRgb(isDark ? '#6366f1' : '#4f46e5');
    };
    let [cr, cg, cb] = getColor();

    function refreshTheme() {
        isDark = detectDark();
        [cr, cg, cb] = getColor();
    }

    const observer = new MutationObserver(refreshTheme);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class', 'data-theme'] });

    const startTime = performance.now();

    function frame() {
        if (!running || !ctx) return;

        const dpr = window.devicePixelRatio || 1;
        const w = container.clientWidth;
        const h = container.clientHeight;

        if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
            canvas.width = w * dpr;
            canvas.height = h * dpr;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }

        ctx.clearRect(0, 0, w, h);

        // Smooth cursor interpolation (matches Chrome CSS transition ~0.3s)
        const dt = 1 / 60; // approximate frame time
        const lerpFactor = 1 - Math.pow(1 - dt * LERP_SPEED, 3); // cubic ease-out
        cursorX += (targetX - cursorX) * lerpFactor;
        cursorY += (targetY - cursorY) * lerpFactor;

        if (drawBackground) {
            const bgGrad = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.6);
            if (isDark) {
                bgGrad.addColorStop(0, '#1e1b4b');
                bgGrad.addColorStop(1, '#0a0a0c');
            } else {
                bgGrad.addColorStop(0, '#e0e7ff');
                bgGrad.addColorStop(1, '#f8fafc');
            }
            ctx.fillStyle = bgGrad;
            ctx.fillRect(0, 0, w, h);
        }

        const t = ((performance.now() - startTime) / 1000) * 0.5;
        renderFn(ctx, w, h, cursorX, cursorY, t, isDark, cr, cg, cb, config.seed);

        requestAnimationFrame(frame);
    }

    requestAnimationFrame(frame);

    return () => {
        running = false;
        observer.disconnect();
        container.removeEventListener('pointermove', onPointer);
        container.removeEventListener('touchmove', onTouch);
        container.removeEventListener('pointerleave', onLeave);
        if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
    };
}

// ============================================================
// Renderer: verbium-particles
// ============================================================
// Hash function identical to worklet (used for w1Dir, not from PRNG sequence)
function hashSeed(n: number): number {
    const x = Math.sin(n) * 43758.5453123;
    return x - Math.floor(x);
}

function createVerbiumRenderer(seed: number) {
    // Match worklet _ensureSeedConstants exactly:
    // randomInt(min,max) = Math.floor(rng() * (max-min+1)) + min
    const rng = mulberry32(seed);
    const w1Freq = Math.floor(rng() * 5) + 2;     // randomInt(2, 6)
    const w1Speed = Math.floor(rng() * 2) + 1;     // randomInt(1, 2)
    const w1Dir = hashSeed(seed + 10) > 0.5 ? 1 : -1;  // hash(seed+10), NOT rng()
    const w2Freq = Math.floor(rng() * 6) + 2;      // randomInt(2, 7)
    const w2Speed = 1;
    const w2Dir = -w1Dir;
    const rowTwist = 0.2 + rng() * 0.4;            // randomFloat(0.2, 0.6)
    const amplitude = Math.floor(rng() * 13) + 10;  // randomInt(10, 22)

    const NUM_PARTICLES = 120;
    const NUM_ROWS = 30;
    const PARTICLE_SIZE = 2.8;
    const MIN_ALPHA = 0.08;
    const MAX_ALPHA = 0.95;

    // CSS values from hero-section.tsx: --ring-radius: 140, --ring-thickness: 380
    const CSS_RING_RADIUS = 140;
    const CSS_RING_THICKNESS = 380;

    return (ctx: CanvasRenderingContext2D, w: number, h: number, cursorX: number, cursorY: number, tRaw: number, _isDark: boolean, cr: number, cg: number, cb: number) => {
        // Match worklet: animTick (0→1 in 6s) * 2π → 6-second cycle
        const elapsed = tRaw * 2;
        const t = ((elapsed % 6) / 6) * Math.PI * 2;
        const minDim = Math.min(w, h);

        // ringBreathe: 6s ease-in-out infinite alternate (120→200→120 over 12s)
        const breatheCycle = (elapsed % 12) / 12;
        const breatheLinear = breatheCycle < 0.5 ? breatheCycle * 2 : 2 - breatheCycle * 2;
        // ease-in-out cubic approximation
        const breatheEased = breatheLinear < 0.5
            ? 2 * breatheLinear * breatheLinear
            : 1 - Math.pow(-2 * breatheLinear + 2, 2) / 2;
        const innerRadius = 120 + (200 - 120) * breatheEased;
        const thickness = CSS_RING_THICKNESS;
        const outerRadius = innerRadius + thickness;
        const halfThick = thickness / 2;

        const cx = w * (0.425 + cursorX * 0.15);
        const cy = h * (0.425 + cursorY * 0.15);
        const cursorPx = cursorX * w;
        const cursorPy = cursorY * h;
        const repulsionRadius = minDim * 0.22;
        const repulsionStrength = 80;

        const cr2 = Math.min(255, cr + 80);
        const cg2 = Math.max(0, cg - 30);
        const cb2 = Math.min(255, cb + 40);
        const colorPulse = (Math.sin(t * 0.3) + 1) * 0.5;

        // Ambient glow
        const glowR = (innerRadius + outerRadius) * 0.5;
        const glowGrad = ctx.createRadialGradient(cx, cy, glowR * 0.3, cx, cy, glowR * 1.2);
        const ga = 0.04 + colorPulse * 0.02;
        const mr = Math.round(cr + (cr2 - cr) * colorPulse);
        const mg = Math.round(cg + (cg2 - cg) * colorPulse);
        const mb = Math.round(cb + (cb2 - cb) * colorPulse);
        glowGrad.addColorStop(0, `rgba(${mr},${mg},${mb},${ga})`);
        glowGrad.addColorStop(0.5, `rgba(${mr},${mg},${mb},${ga * 0.5})`);
        glowGrad.addColorStop(1, `rgba(${mr},${mg},${mb},0)`);
        ctx.fillStyle = glowGrad;
        ctx.fillRect(0, 0, w, h);

        // Cursor glow
        const cgRad = minDim * 0.15;
        const cGrad = ctx.createRadialGradient(cursorPx, cursorPy, 0, cursorPx, cursorPy, cgRad);
        cGrad.addColorStop(0, `rgba(${cr2},${cg2},${cb2},0.08)`);
        cGrad.addColorStop(0.4, `rgba(${cr},${cg},${cb},0.03)`);
        cGrad.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
        ctx.fillStyle = cGrad;
        ctx.fillRect(0, 0, w, h);

        // Ring particles
        const positions: number[] = [];
        const connThresh = minDim * 0.06;

        for (let r = 0; r < NUM_ROWS; r++) {
            const rowP = NUM_ROWS > 1 ? r / (NUM_ROWS - 1) : 0;
            const baseR = innerRadius + rowP * thickness;

            for (let i = 0; i < NUM_PARTICLES; i++) {
                const angle = (i / NUM_PARTICLES) * Math.PI * 2;
                const wave1 = Math.sin(angle * w1Freq + t * w1Speed * w1Dir);
                const wave2 = Math.sin(angle * w2Freq + t * w2Speed * w2Dir);
                const rowOff = Math.sin(r * rowTwist + t);
                const waveH = wave1 + wave2 + rowOff;

                let norm = (waveH + 3) / 6;
                norm = Math.pow(Math.max(0, norm), 1.5);
                let alpha = MIN_ALPHA + norm * (MAX_ALPHA - MIN_ALPHA);

                const distortion = waveH * amplitude;
                const finalR = baseR + distortion;
                let x = cx + Math.cos(angle) * finalR;
                let y = cy + Math.sin(angle) * finalR;

                const dx = x - cursorPx;
                const dy = y - cursorPy;
                const dist = Math.sqrt(dx * dx + dy * dy);
                let drawSize = PARTICLE_SIZE;

                if (dist < repulsionRadius && dist > 0.1) {
                    const falloff = Math.pow(1 - dist / repulsionRadius, 3);
                    x += (dx / dist) * repulsionStrength * falloff;
                    y += (dy / dist) * repulsionStrength * falloff;
                    alpha = Math.min(1, alpha + falloff * 0.4);
                    drawSize = PARTICLE_SIZE + (1 - dist / repulsionRadius) * PARTICLE_SIZE * 1.2;
                }

                const dInner = finalR - innerRadius;
                const dOuter = outerRadius - finalR;
                const vis = Math.max(0, Math.min(1, Math.min(dInner, dOuter) / halfThick));
                alpha = Math.max(0, Math.min(1, alpha * vis));

                let colorMix = colorPulse * norm;
                if (dist < repulsionRadius) {
                    colorMix = Math.min(1, colorMix + (1 - dist / repulsionRadius) * 0.5);
                }
                const pr = Math.round(cr + (cr2 - cr) * colorMix);
                const pg = Math.round(cg + (cg2 - cg) * colorMix);
                const pb = Math.round(cb + (cb2 - cb) * colorMix);

                if (alpha > 0.01) {
                    const sprite = getParticleSprite(pr, pg, pb, alpha, drawSize);
                    ctx.drawImage(sprite, x - sprite.width / 2, y - sprite.height / 2);

                    if (alpha > 0.15 && i % 3 === 0 && r % 2 === 0) {
                        positions.push(x, y, alpha);
                    }
                }
            }
        }

        // Constellation connections
        ctx.lineWidth = 0.5;
        const numPts = positions.length / 3;
        for (let a = 0; a < numPts; a++) {
            const ax = positions[a * 3];
            const ay = positions[a * 3 + 1];
            const aA = positions[a * 3 + 2];
            for (let b = a + 1; b < numPts; b++) {
                const bx = positions[b * 3];
                const by = positions[b * 3 + 1];
                const bA = positions[b * 3 + 2];
                const ddx = ax - bx;
                const ddy = ay - by;
                const d = Math.sqrt(ddx * ddx + ddy * ddy);
                if (d < connThresh) {
                    const la = (1 - d / connThresh) * Math.min(aA, bA) * 0.25;
                    if (la > 0.01) {
                        ctx.strokeStyle = `rgba(${cr},${cg},${cb},${la})`;
                        ctx.beginPath();
                        ctx.moveTo(ax, ay);
                        ctx.lineTo(bx, by);
                        ctx.stroke();
                    }
                }
            }
        }

        // Cursor orbit ring
        const dxC = cursorPx - cx;
        const dyC = cursorPy - cy;
        const distCenter = Math.sqrt(dxC * dxC + dyC * dyC);
        const orbitIntensity = Math.min(1, distCenter / (minDim * 0.3));

        // Orbit ring — worklet always draws particles, only gates glow on intensity
        const orbitRadius = minDim * 0.05;
        const orbitThickness = minDim * 0.09;
        const orbitOuterR = orbitRadius + orbitThickness;
        const orbitHalfThick = orbitThickness / 2;
        const orbitRows = 8;
        const orbitParts = 60;
        const orbitSize = PARTICLE_SIZE * 0.65;
        const orbitT = t * 1.5;

        const oCr = Math.min(255, cr + 70);
        const oCg = Math.min(255, cg + 70);
        const oCb = Math.min(255, cb + 40);

        // Glow only when cursor is away from center (matches worklet)
        if (orbitIntensity > 0.1) {
            const oGlowRad = orbitOuterR * 1.5;
            const oGlow = ctx.createRadialGradient(cursorPx, cursorPy, 0, cursorPx, cursorPy, oGlowRad);
            oGlow.addColorStop(0, `rgba(${oCr},${oCg},${oCb},${0.06 * orbitIntensity})`);
            oGlow.addColorStop(1, `rgba(${oCr},${oCg},${oCb},0)`);
            ctx.fillStyle = oGlow;
            ctx.beginPath();
            ctx.arc(cursorPx, cursorPy, oGlowRad, 0, Math.PI * 2);
            ctx.fill();
        }

        // Orbit particles always drawn (intensity affects alpha, not visibility gate)
        for (let or2 = 0; or2 < orbitRows; or2++) {
            const oRowP = orbitRows > 1 ? or2 / (orbitRows - 1) : 0;
            const oBaseR = orbitRadius + oRowP * orbitThickness;

            for (let oi = 0; oi < orbitParts; oi++) {
                const oAngle = (oi / orbitParts) * Math.PI * 2;
                const oW1 = Math.sin(oAngle * 3 + orbitT * 2);
                const oW2 = Math.sin(oAngle * 5 - orbitT * 1.3);
                const oRowOff = Math.sin(or2 * 0.5 + orbitT);
                const oWH = oW1 + oW2 + oRowOff;

                let oNorm = (oWH + 3) / 6;
                oNorm = Math.pow(Math.max(0, oNorm), 1.2);
                let oAlpha = 0.15 + oNorm * 0.7 * orbitIntensity;

                const oDistortion = oWH * 7;
                const oFinalR = oBaseR + oDistortion;
                const ox = cursorPx + Math.cos(oAngle) * oFinalR;
                const oy = cursorPy + Math.sin(oAngle) * oFinalR;

                const oDistIn = oFinalR - orbitRadius;
                const oDistOut = orbitOuterR - oFinalR;
                const oVis = Math.max(0, Math.min(1, Math.min(oDistIn, oDistOut) / orbitHalfThick));
                oAlpha = Math.max(0, Math.min(1, oAlpha * oVis));

                if (oAlpha > 0.01) {
                    const oColorMix = oNorm * 0.6;
                    const opr = Math.round(oCr + (255 - oCr) * oColorMix * 0.3);
                    const opg = Math.round(oCg + (255 - oCg) * oColorMix * 0.2);
                    const opb = Math.round(oCb + (255 - oCb) * oColorMix * 0.1);

                    const sprite = getParticleSprite(opr, opg, opb, oAlpha, orbitSize);
                    ctx.drawImage(sprite, ox - sprite.width / 2, oy - sprite.height / 2);
                }
            }
        }
    };
}

// ============================================================
// Renderer: nebula-flow
// ============================================================
function noise2D(x: number, y: number): number {
    return (
        Math.sin(x * 1.2 + y * 0.9) * 0.3 +
        Math.sin(x * 0.7 - y * 1.3) * 0.25 +
        Math.sin(x * 2.1 + y * 1.7) * 0.15 +
        Math.sin(x * 0.5 + y * 2.3) * 0.2 +
        Math.sin(x * 3.1 - y * 0.4) * 0.1
    );
}

const renderNebulaFlow: RenderFn = (ctx, w, h, cursorX, cursorY, t, _isDark, cr, cg, cb, seed) => {
    const cr2 = Math.min(255, cr + 60);
    const cg2 = Math.max(0, cg - 40);
    const cb2 = Math.min(255, cb + 80);
    const cr3 = Math.min(255, cr + 120);
    const cg3 = Math.min(255, cg + 40);
    const cb3 = Math.max(0, cb - 60);

    const cursorPx = cursorX * w;
    const cursorPy = cursorY * h;
    const cursorRad = Math.min(w, h) * 0.25;

    const cellSize = 6;
    const cols = Math.ceil(w / cellSize);
    const rows = Math.ceil(h / cellSize);
    // Worklet uses: animTick (0→1 in 6s) * 2π → 6-second cycle.
    // Framework t = elapsed * 0.5, so elapsed = t * 2.
    const elapsed = t * 2;
    const tAnim = ((elapsed % 6) / 6) * Math.PI * 2;

    for (let gy = 0; gy < rows; gy++) {
        for (let gx = 0; gx < cols; gx++) {
            const px = gx * cellSize;
            const py = gy * cellSize;
            const nx = gx / cols;
            const ny = gy / rows;

            const n1 = noise2D(nx * 4 + tAnim * 0.4 + seed, ny * 3 - tAnim * 0.3);
            const n2 = noise2D(nx * 8 - tAnim * 0.2, ny * 6 + tAnim * 0.5 + seed * 0.5);
            const n3 = noise2D(nx * 2 + tAnim * 0.15, ny * 2 + tAnim * 0.1);

            let combined = n1 * 0.5 + n2 * 0.3 + n3 * 0.2;

            const dx = px - cursorPx;
            const dy = py - cursorPy;
            const dist = Math.sqrt(dx * dx + dy * dy);

            if (dist < cursorRad) {
                const factor = Math.pow(1 - dist / cursorRad, 2);
                combined += factor * 0.4 * Math.sin(tAnim * 2 + dist * 0.02);
            }

            let alpha = 0;
            if (combined > 0.05) alpha = (combined - 0.05) * 0.18;
            if (alpha > 0.12) alpha = 0.12;

            if (alpha > 0.005) {
                const blend1 = (n1 + 1) * 0.5;
                const blend2 = (n3 + 1) * 0.5;

                let fr: number, fg: number, fb: number;
                if (blend1 > 0.5) {
                    const m = (blend1 - 0.5) * 2;
                    fr = Math.round(cr + (cr2 - cr) * m);
                    fg = Math.round(cg + (cg2 - cg) * m);
                    fb = Math.round(cb + (cb2 - cb) * m);
                } else {
                    const m2 = blend2;
                    fr = Math.round(cr + (cr3 - cr) * m2 * 0.4);
                    fg = Math.round(cg + (cg3 - cg) * m2 * 0.4);
                    fb = Math.round(cb + (cb3 - cb) * m2 * 0.4);
                }

                ctx.fillStyle = `rgba(${fr},${fg},${fb},${alpha})`;
                ctx.fillRect(px, py, cellSize, cellSize);
            }
        }
    }

    // Central glow
    const glowX = w * 0.5;
    const glowY = h * 0.4;
    const glowR = Math.min(w, h) * 0.4;
    const glow = ctx.createRadialGradient(glowX, glowY, 0, glowX, glowY, glowR);
    glow.addColorStop(0, `rgba(${cr},${cg},${cb},0.05)`);
    glow.addColorStop(0.5, `rgba(${cr2},${cg2},${cb2},0.02)`);
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);
};

// ============================================================
// Renderer: grid-pulse
// ============================================================
const renderGridPulse: RenderFn = (ctx, w, h, cursorX, cursorY, t, _isDark, cr, cg, cb, seed) => {
    const cursorPx = cursorX * w;
    const cursorPy = cursorY * h;

    const spacing = 32;
    const cols = Math.ceil(w / spacing) + 1;
    const rows = Math.ceil(h / spacing) + 1;
    const baseRadius = 1.2;
    const maxRadius = 3.5;

    const pulseRadius = Math.min(w, h) * 0.35;
    const waveSpeed = 2.5;
    const waveWidth = Math.min(w, h) * 0.12;

    const elapsed = t * 2;
    const tAnim = ((elapsed % 6) / 6) * Math.PI * 2;
    const ambientWaveAngle = tAnim * 0.2 + seed;
    const ambientWaveDirX = Math.cos(ambientWaveAngle);
    const ambientWaveDirY = Math.sin(ambientWaveAngle);

    for (let gy = 0; gy < rows; gy++) {
        for (let gx = 0; gx < cols; gx++) {
            const px = gx * spacing;
            const py = gy * spacing;

            const dx = px - cursorPx;
            const dy = py - cursorPy;
            const dist = Math.sqrt(dx * dx + dy * dy);

            const pulsePhase = dist - tAnim * pulseRadius * waveSpeed;
            const pulseFactor = Math.exp(-Math.abs(pulsePhase % (pulseRadius * 2)) / waveWidth);

            let proximityFactor = 0;
            if (dist < pulseRadius) {
                proximityFactor = Math.pow(1 - dist / pulseRadius, 2);
            }

            const dotProduct = px * ambientWaveDirX + py * ambientWaveDirY;
            const ambientPhase = Math.sin(dotProduct * 0.015 + tAnim * 1.5);
            const ambientFactor = (ambientPhase + 1) * 0.5;

            const sizeFactor = 0.3 + ambientFactor * 0.4 + pulseFactor * 0.6 + proximityFactor * 0.8;
            const dotRadius = baseRadius + (maxRadius - baseRadius) * Math.min(1, sizeFactor);

            let alpha = 0.06 + ambientFactor * 0.08 + pulseFactor * 0.3 + proximityFactor * 0.4;
            if (alpha > 0.6) alpha = 0.6;

            const colorShift = proximityFactor + pulseFactor * 0.5;
            const dr = Math.round(cr + (255 - cr) * colorShift * 0.3);
            const dg = Math.round(cg + (255 - cg) * colorShift * 0.2);
            const db = Math.round(cb + (255 - cb) * colorShift * 0.15);

            if (alpha > 0.02) {
                const sprite = getParticleSprite(dr, dg, db, alpha, dotRadius);
                ctx.drawImage(sprite, px - sprite.width / 2, py - sprite.height / 2);
            }

            // Connection lines near cursor
            if (proximityFactor > 0.2 && gx < cols - 1 && gy < rows - 1) {
                const lineAlpha = proximityFactor * 0.12;
                ctx.strokeStyle = `rgba(${cr},${cg},${cb},${lineAlpha})`;
                ctx.lineWidth = 0.5;
                ctx.beginPath();
                ctx.moveTo(px, py);
                ctx.lineTo(px + spacing, py);
                ctx.stroke();
                ctx.beginPath();
                ctx.moveTo(px, py);
                ctx.lineTo(px, py + spacing);
                ctx.stroke();
            }
        }
    }

    // Cursor glow
    const glowR = pulseRadius * 0.6;
    const glow = ctx.createRadialGradient(cursorPx, cursorPy, 0, cursorPx, cursorPy, glowR);
    glow.addColorStop(0, `rgba(${cr},${cg},${cb},0.06)`);
    glow.addColorStop(0.5, `rgba(${cr},${cg},${cb},0.02)`);
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);
};

// ============================================================
// Renderer: wave-field
// ============================================================
const renderWaveField: RenderFn = (ctx, w, h, cursorX, cursorY, t, _isDark, cr, cg, cb, seed) => {
    const cr2 = Math.min(255, cr + 50);
    const cg2 = Math.min(255, cg + 80);
    const cb2 = Math.max(0, cb - 30);
    const cr3 = Math.max(0, cr - 30);
    const cg3 = Math.min(255, cg + 20);
    const cb3 = Math.min(255, cb + 60);

    const cursorPx = cursorX * w;
    const cursorPy = cursorY * h;
    const cursorInfluence = Math.min(w, h) * 0.3;

    const numWaves = 7;
    const stepX = 3;
    const elapsed = t * 2;
    const tAnim = ((elapsed % 6) / 6) * Math.PI * 2;

    for (let waveIdx = 0; waveIdx < numWaves; waveIdx++) {
        const waveY = h * (0.2 + (waveIdx / (numWaves - 1)) * 0.6);
        const freq = 0.003 + waveIdx * 0.001;
        const amp = 30 + waveIdx * 8;
        const speed = (0.5 + waveIdx * 0.15) * (waveIdx % 2 === 0 ? 1 : -1);
        const phase = seed + waveIdx * 1.7;

        const waveBlend = waveIdx / (numWaves - 1);
        let wr: number, wg: number, wb: number;
        if (waveBlend < 0.5) {
            const m = waveBlend * 2;
            wr = Math.round(cr + (cr2 - cr) * m);
            wg = Math.round(cg + (cg2 - cg) * m);
            wb = Math.round(cb + (cb2 - cb) * m);
        } else {
            const m2 = (waveBlend - 0.5) * 2;
            wr = Math.round(cr2 + (cr3 - cr2) * m2);
            wg = Math.round(cg2 + (cg3 - cg2) * m2);
            wb = Math.round(cb2 + (cb3 - cb2) * m2);
        }

        ctx.beginPath();
        let firstY: number | null = null;

        for (let px = 0; px <= w; px += stepX) {
            let y = waveY +
                Math.sin(px * freq + tAnim * speed + phase) * amp +
                Math.sin(px * freq * 2.3 - tAnim * speed * 0.7 + phase * 1.3) * (amp * 0.4) +
                Math.sin(px * freq * 0.5 + tAnim * speed * 1.5) * (amp * 0.25);

            const dx = px - cursorPx;
            const dy = y - cursorPy;
            const dist = Math.sqrt(dx * dx + dy * dy);
            if (dist < cursorInfluence) {
                const factor = Math.pow(1 - dist / cursorInfluence, 3);
                y += (cursorPy - y) * factor * 0.4;
            }

            if (firstY === null) {
                firstY = y;
                ctx.moveTo(px, y);
            } else {
                ctx.lineTo(px, y);
            }
        }

        const baseAlpha = 0.06 + (1 - Math.abs(waveBlend - 0.5) * 2) * 0.06;
        ctx.strokeStyle = `rgba(${wr},${wg},${wb},${baseAlpha})`;
        ctx.lineWidth = 1.5 + (1 - Math.abs(waveBlend - 0.5) * 2) * 1;
        ctx.stroke();

        ctx.lineTo(w, h);
        ctx.lineTo(0, h);
        ctx.closePath();
        const fillAlpha = 0.012 + (1 - Math.abs(waveBlend - 0.5) * 2) * 0.008;
        ctx.fillStyle = `rgba(${wr},${wg},${wb},${fillAlpha})`;
        ctx.fill();
    }

    // Interference dots at wave crossings
    const dotSpacing = 24;
    const dotCols = Math.ceil(w / dotSpacing);
    for (let dc = 0; dc < dotCols; dc++) {
        const dpx = dc * dotSpacing + dotSpacing * 0.5;
        const waveVals: number[] = [];
        for (let wi = 0; wi < numWaves; wi++) {
            const dWaveY = h * (0.2 + (wi / (numWaves - 1)) * 0.6);
            const dFreq = 0.003 + wi * 0.001;
            const dAmp = 30 + wi * 8;
            const dSpeed = (0.5 + wi * 0.15) * (wi % 2 === 0 ? 1 : -1);
            const dPhase = seed + wi * 1.7;
            const yVal = dWaveY +
                Math.sin(dpx * dFreq + tAnim * dSpeed + dPhase) * dAmp +
                Math.sin(dpx * dFreq * 2.3 - tAnim * dSpeed * 0.7 + dPhase * 1.3) * (dAmp * 0.4);
            waveVals.push(yVal);
        }

        for (let wa = 0; wa < waveVals.length; wa++) {
            for (let wb2 = wa + 1; wb2 < waveVals.length; wb2++) {
                const gap = Math.abs(waveVals[wa] - waveVals[wb2]);
                if (gap < 15) {
                    const midY = (waveVals[wa] + waveVals[wb2]) * 0.5;
                    const dotAlpha = (1 - gap / 15) * 0.2;
                    const dotR = 2 + (1 - gap / 15) * 2;
                    const sprite = getParticleSprite(cr, cg, cb, dotAlpha, dotR);
                    ctx.drawImage(sprite, dpx - sprite.width / 2, midY - sprite.height / 2);
                }
            }
        }
    }
};

// ============================================================
// Renderer dispatch
// ============================================================
function getRenderer(worklet: WorkletName, seed: number): RenderFn {
    switch (worklet) {
        case 'verbium-particles': return createVerbiumRenderer(seed);
        case 'nebula-flow': return renderNebulaFlow;
        case 'grid-pulse': return renderGridPulse;
        case 'wave-field': return renderWaveField;
    }
}

// ============================================================
// Hook
// ============================================================
export interface VorbiumPaintOptions {
    seed?: number;
    color?: string;
}

export function useVorbiumPaint(
    ref: React.RefObject<HTMLElement | null>,
    worklet: WorkletName = 'verbium-particles',
    options?: VorbiumPaintOptions,
) {
    const [hasPaintWorklet, setHasPaintWorklet] = useState<boolean | null>(null);

    useEffect(() => {
        const supported = supportsPaintWorklet();
        setHasPaintWorklet(supported);

        if (supported) {
            loadWorklet(worklet);
        }

        const el = ref.current;
        if (!el) return;

        // --- Safari/Firefox: Canvas fallback ---
        if (!supported) {
            const seed = options?.seed ?? 42;
            const renderFn = getRenderer(worklet, seed);
            const drawBg = worklet === 'verbium-particles';
            return createCanvasFallback(el, renderFn, { seed, colorOverride: options?.color }, drawBg);
        }

        // --- Chrome: worklet cursor tracking ---
        let raf = 0;
        let lastX = 0.5, lastY = 0.5;

        const update = () => {
            raf = 0;
            el.style.setProperty("--cursor-x", String(lastX));
            el.style.setProperty("--cursor-y", String(lastY));
        };

        const onMove = (ev: PointerEvent) => {
            const rect = el.getBoundingClientRect();
            lastX = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
            lastY = Math.max(0, Math.min(1, (ev.clientY - rect.top) / rect.height));
            if (!raf) raf = requestAnimationFrame(update);
        };

        const onLeave = () => {
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
    }, [ref, worklet, options?.seed, options?.color]);

    return { hasPaintWorklet };
}
