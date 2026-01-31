/*
  Vorbium "Torus Particles" Paint Worklet

  A monochrome 3D torus made of dots (similar to the reference screenshot), with
  subtle motion and pointer-driven parallax.

  Usage (CSS):
    background-image: paint(vorbium-torus);

  Variables (all optional):
    --torus-x: <number>         0..100 (center X in % of element width)
    --torus-y: <number>         0..100 (center Y in % of element height)
    --torus-radius: <number>    px (major radius)
    --torus-tube: <number>      px (minor radius)
    --torus-rings: <number>     segments around major ring
    --torus-tubes: <number>     segments around tube
    --torus-dot-size: <number>  px base dot size
    --torus-dot-color: <color>
    --torus-min-alpha: <number> 0..1
    --torus-max-alpha: <number> 0..1
    --torus-seed: <number>
    --tick: <number>            ms-ish (driven from JS)
*/

class VorbiumTorusPainter {
  static get inputProperties() {
    return [
      '--torus-x',
      '--torus-y',
      '--torus-radius',
      '--torus-tube',
      '--torus-rings',
      '--torus-tubes',
      '--torus-dot-size',
      '--torus-dot-color',
      '--torus-min-alpha',
      '--torus-max-alpha',
      '--torus-seed',
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

    const cxPct = readNum('--torus-x', 50);
    const cyPct = readNum('--torus-y', 50);
    const seed = readNum('--torus-seed', 42);
    const tick = readNum('--tick', 0);

    const major = Math.max(40, readNum('--torus-radius', Math.min(w, h) * 0.28));
    const tube = Math.max(20, readNum('--torus-tube', major * 0.42));
    const rings = Math.max(48, Math.floor(readNum('--torus-rings', 170)));
    const tubes = Math.max(18, Math.floor(readNum('--torus-tubes', 64)));
    const dotBase = Math.max(0.6, readNum('--torus-dot-size', 1.6));
    const minA = Math.max(0, Math.min(1, readNum('--torus-min-alpha', 0.08)));
    const maxA = Math.max(minA, Math.min(1, readNum('--torus-max-alpha', 1)));

    const color = (props.get('--torus-dot-color') || '').toString().trim() || '#ffffff';

    const cx = (cxPct / 100) * w;
    const cy = (cyPct / 100) * h;

    // Cheap deterministic pseudo-random that is stable per particle
    const rand = (i, s) => {
      const x = Math.sin(i * 12.9898 + s * 78.233 + seed) * 43758.5453;
      return x - Math.floor(x);
    };

    // Time
    const t = tick * 0.00025;

    // Pointer parallax (tilt + roll)
    const mx = (cxPct - 50) / 50; // -1..1
    const my = (cyPct - 50) / 50; // -1..1

    const rotY = t * 0.75 + mx * 0.55;
    const rotX = 0.62 + my * 0.32 + Math.sin(t * 0.9) * 0.06;
    const rotZ = -0.32 + mx * 0.18 + Math.cos(t * 0.7) * 0.05;

    const fov = 560;

    // Subtle vignette (adds depth behind the torus)
    ctx.save();
    ctx.globalCompositeOperation = 'source-over';
    const g = ctx.createRadialGradient(cx, cy, major * 0.25, cx, cy, major + tube * 2.2);
    g.addColorStop(0, 'rgba(255,255,255,0.00)');
    g.addColorStop(0.55, 'rgba(255,255,255,0.03)');
    g.addColorStop(1, 'rgba(255,255,255,0.10)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    ctx.restore();

    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    ctx.fillStyle = color;

    const total = rings * tubes;

    for (let idx = 0; idx < total; idx += 1) {
      const i = Math.floor(idx / tubes);
      const j = idx - i * tubes;

      const u = (i / rings) * Math.PI * 2 + t * (0.08 + rand(idx, 1.1) * 0.18);
      const v = (j / tubes) * Math.PI * 2 + t * 0.22;

      // Torus parametric surface
      let x = (major + tube * Math.cos(v)) * Math.cos(u);
      let y = (major + tube * Math.cos(v)) * Math.sin(u);
      let z = tube * Math.sin(v);

      // Rotate X
      {
        const y1 = y * Math.cos(rotX) - z * Math.sin(rotX);
        const z1 = y * Math.sin(rotX) + z * Math.cos(rotX);
        y = y1;
        z = z1;
      }
      // Rotate Y
      {
        const x1 = x * Math.cos(rotY) + z * Math.sin(rotY);
        const z1 = -x * Math.sin(rotY) + z * Math.cos(rotY);
        x = x1;
        z = z1;
      }
      // Rotate Z
      {
        const x1 = x * Math.cos(rotZ) - y * Math.sin(rotZ);
        const y1 = x * Math.sin(rotZ) + y * Math.cos(rotZ);
        x = x1;
        y = y1;
      }

      // Project to 2D
      const scale = fov / (fov + z + 180);
      const px = cx + x * scale;
      const py = cy + y * scale;

      // Depth shading
      const depth = Math.max(0, Math.min(1, (z + tube * 1.4) / (tube * 2.8)));
      const aRand = minA + (maxA - minA) * rand(idx, 2.2);
      const a = Math.min(1, aRand * (0.20 + scale * 0.95) * (0.35 + depth));

      if (a <= 0.01) continue;

      const s = dotBase * (0.65 + scale * 1.75) * (0.7 + rand(idx, 3.3) * 0.9);

      ctx.globalAlpha = a;
      ctx.beginPath();
      ctx.arc(px, py, s, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.restore();
  }
}

registerPaint('vorbium-torus', VorbiumTorusPainter);

