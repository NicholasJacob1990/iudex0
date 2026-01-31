/*
  Vorbium "Halo Particles" Paint Worklet

  Goal: a ring/halo of particles with subtle motion that can follow the cursor.

  CSS vars (all optional):
    --halo-x: <number>  (0..100, percent of element width)
    --halo-y: <number>  (0..100, percent of element height)
    --halo-radius: <number>      (px)
    --halo-thickness: <number>   (px, full band thickness)
    --halo-particle-count: <number> (particles per radial row)
    --halo-particle-rows: <number>  (radial rows)
    --halo-particle-size: <number>  (px)
    --halo-particle-color: <color>
    --halo-min-alpha: <number> (0..1)
    --halo-max-alpha: <number> (0..1)
    --halo-seed: <number>
    --tick: <number> (ms-ish)
*/

class VorbiumHaloParticlesPainter {
  static get inputProperties() {
    return [
      '--halo-x',
      '--halo-y',
      '--halo-radius',
      '--halo-thickness',
      '--halo-particle-count',
      '--halo-particle-rows',
      '--halo-particle-size',
      '--halo-particle-color',
      '--halo-min-alpha',
      '--halo-max-alpha',
      '--halo-seed',
      '--tick',
    ];
  }

  paint(ctx, geom, props) {
    const w = geom.width;
    const h = geom.height;

    const readNum = (name, fallback) => {
      const v = props.get(name);
      if (!v) return fallback;
      const s = v.toString().trim();
      if (!s) return fallback;
      const n = parseFloat(s);
      return Number.isFinite(n) ? n : fallback;
    };

    const haloXPct = readNum('--halo-x', 50);
    const haloYPct = readNum('--halo-y', 50);
    const baseRadius = readNum('--halo-radius', 210);
    const thickness = readNum('--halo-thickness', 260);
    const particlesPerRow = Math.max(16, Math.floor(readNum('--halo-particle-count', 80)));
    const rows = Math.max(6, Math.floor(readNum('--halo-particle-rows', 18)));
    const particleSize = Math.max(0.8, readNum('--halo-particle-size', 2));
    const minAlpha = Math.max(0, Math.min(1, readNum('--halo-min-alpha', 0.08)));
    const maxAlpha = Math.max(minAlpha, Math.min(1, readNum('--halo-max-alpha', 0.55)));
    const seed = readNum('--halo-seed', 1337);
    const tick = readNum('--tick', 0);

    const color = (props.get('--halo-particle-color') || '').toString().trim() || '#6366f1';

    const cx = (haloXPct / 100) * w;
    const cy = (haloYPct / 100) * h;

    const total = particlesPerRow * rows;

    // Deterministic pseudo-random (fast, stable per paint)
    const rand = (i, s) => {
      const x = Math.sin(i * 12.9898 + s * 78.233 + seed) * 43758.5453;
      return x - Math.floor(x);
    };

    const phase = tick * 0.001;
    const breathe = Math.sin(phase * 0.8) * 18; // gentle radius breathing
    const drift = phase * 0.18; // slow angular drift

    // Soft vignette to give depth
    ctx.save();
    ctx.globalCompositeOperation = 'source-over';
    const g = ctx.createRadialGradient(cx, cy, baseRadius * 0.5, cx, cy, baseRadius + thickness);
    g.addColorStop(0, 'rgba(255,255,255,0.00)');
    g.addColorStop(1, 'rgba(255,255,255,0.05)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();

    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    ctx.fillStyle = color;

    for (let i = 0; i < total; i++) {
      const row = Math.floor(i / particlesPerRow);
      const col = i - row * particlesPerRow;

      const t = col / particlesPerRow;
      const rowT = rows <= 1 ? 0.5 : row / (rows - 1);

      // angle distribution with subtle per-particle wobble
      const wobble = (rand(i, 1.1) - 0.5) * 0.22 + Math.sin(phase * 0.9 + i * 0.07) * 0.05;
      const ang = t * Math.PI * 2 + drift + wobble;

      // radius distribution across the band + breathing + small animated jitter
      const band = (rowT - 0.5) * thickness;
      const rJitter = (rand(i, 2.2) - 0.5) * (thickness / rows) * 0.6;
      const r = baseRadius + breathe + band + rJitter + Math.sin(phase * 1.3 + i * 0.04) * 6;

      const x = cx + Math.cos(ang) * r;
      const y = cy + Math.sin(ang) * r;

      const a = minAlpha + (maxAlpha - minAlpha) * rand(i, 3.3);
      const s = particleSize * (0.85 + rand(i, 4.4) * 1.35);

      ctx.globalAlpha = a;
      ctx.beginPath();
      ctx.arc(x, y, s, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  }
}

registerPaint('vorbium-halo-particles', VorbiumHaloParticlesPainter);

