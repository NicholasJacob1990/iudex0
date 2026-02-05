/*
  Nebula Flow Worklet
  Flowing organic nebula with layered noise, cursor attraction, and color gradients.
  For marketing/platform pages — a fluid, ethereal effect.
*/

function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    var t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

class NebulaFlow {
  static get inputProperties() {
    return [
      '--cursor-x', '--cursor-y',
      '--t',
      '--animation-tick',
      '--theme-color',
      '--seed',
    ];
  }

  _num(v, fallback) {
    if (!v) return fallback;
    var s = v.toString().trim();
    var n = parseFloat(s);
    return Number.isFinite(n) ? n : fallback;
  }

  _str(v, fallback) {
    if (!v) return fallback;
    var s = v.toString().trim();
    return s.length ? s : fallback;
  }

  _norm01(v) {
    var n = v;
    if (n > 1) n = n / 100;
    return Math.max(0, Math.min(1, n));
  }

  _parseColor(color) {
    var s = String(color).trim();
    if (s.startsWith('#')) {
      var c = s.substring(1);
      if (c.length === 3) c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
      var num = parseInt(c, 16);
      return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
    }
    return [79, 70, 229];
  }

  // Simple 2D noise approximation using sine waves
  noise2D(x, y) {
    return (
      Math.sin(x * 1.2 + y * 0.9) * 0.3 +
      Math.sin(x * 0.7 - y * 1.3) * 0.25 +
      Math.sin(x * 2.1 + y * 1.7) * 0.15 +
      Math.sin(x * 0.5 + y * 2.3) * 0.2 +
      Math.sin(x * 3.1 - y * 0.4) * 0.1
    );
  }

  paint(ctx, geom, props) {
    var w = geom.width;
    var h = geom.height;

    var cursorNx = this._norm01(this._num(props.get('--cursor-x'), 0.5));
    var cursorNy = this._norm01(this._num(props.get('--cursor-y'), 0.5));
    var tRaw = this._num(props.get('--t'), 0);
    var animTick = this._num(props.get('--animation-tick'), 0);
    var themeColor = this._str(props.get('--theme-color'), '#6366f1');
    var seed = this._num(props.get('--seed'), 77);

    var t = animTick > 0 ? animTick * Math.PI * 2 : tRaw * 0.008;

    var rgb = this._parseColor(themeColor);
    var cr = rgb[0], cg = rgb[1], cb = rgb[2];

    // Secondary color
    var cr2 = Math.min(255, cr + 60);
    var cg2 = Math.max(0, cg - 40);
    var cb2 = Math.min(255, cb + 80);

    // Tertiary color (warm accent)
    var cr3 = Math.min(255, cr + 120);
    var cg3 = Math.min(255, cg + 40);
    var cb3 = Math.max(0, cb - 60);

    var cursorPx = cursorNx * w;
    var cursorPy = cursorNy * h;

    // Resolution for the nebula grid
    var cellSize = 6;
    var cols = Math.ceil(w / cellSize);
    var rows = Math.ceil(h / cellSize);

    // Cursor influence radius
    var cursorRad = Math.min(w, h) * 0.25;

    for (var gy = 0; gy < rows; gy++) {
      for (var gx = 0; gx < cols; gx++) {
        var px = gx * cellSize;
        var py = gy * cellSize;

        // Normalized coords
        var nx = gx / cols;
        var ny = gy / rows;

        // Layered noise
        var n1 = this.noise2D(nx * 4 + t * 0.4 + seed, ny * 3 - t * 0.3);
        var n2 = this.noise2D(nx * 8 - t * 0.2, ny * 6 + t * 0.5 + seed * 0.5);
        var n3 = this.noise2D(nx * 2 + t * 0.15, ny * 2 + t * 0.1);

        var combined = n1 * 0.5 + n2 * 0.3 + n3 * 0.2;

        // Cursor attraction — warp the noise near cursor
        var dx = px - cursorPx;
        var dy = py - cursorPy;
        var dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < cursorRad) {
          var factor = 1 - (dist / cursorRad);
          factor = factor * factor;
          combined += factor * 0.4 * Math.sin(t * 2 + dist * 0.02);
        }

        // Map to alpha — only show positive bands
        var alpha = 0;
        if (combined > 0.05) {
          alpha = (combined - 0.05) * 0.18;
        }
        if (alpha > 0.12) alpha = 0.12;

        if (alpha > 0.005) {
          // Color blend based on noise layers
          var blend1 = (n1 + 1) * 0.5;
          var blend2 = (n3 + 1) * 0.5;

          var fr, fg, fb;
          if (blend1 > 0.5) {
            var m = (blend1 - 0.5) * 2;
            fr = Math.round(cr + (cr2 - cr) * m);
            fg = Math.round(cg + (cg2 - cg) * m);
            fb = Math.round(cb + (cb2 - cb) * m);
          } else {
            var m2 = blend2;
            fr = Math.round(cr + (cr3 - cr) * m2 * 0.4);
            fg = Math.round(cg + (cg3 - cg) * m2 * 0.4);
            fb = Math.round(cb + (cb3 - cb) * m2 * 0.4);
          }

          ctx.fillStyle = 'rgba(' + fr + ',' + fg + ',' + fb + ',' + alpha + ')';
          ctx.fillRect(px, py, cellSize, cellSize);
        }
      }
    }

    // Central glow
    var glowX = w * 0.5;
    var glowY = h * 0.4;
    var glowR = Math.min(w, h) * 0.4;
    var glow = ctx.createRadialGradient(glowX, glowY, 0, glowX, glowY, glowR);
    glow.addColorStop(0, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.05)');
    glow.addColorStop(0.5, 'rgba(' + cr2 + ',' + cg2 + ',' + cb2 + ',0.02)');
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);
  }
}

registerPaint('nebula-flow', NebulaFlow);
