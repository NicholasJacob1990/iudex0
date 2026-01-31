/*
  Vorbium Dual Ring Particles Worklet
  Two rings: a large static ring at center + a smaller dynamic orbit that follows the cursor.
  The cursor creates a gravitational lens effect: particles from the static ring spread apart,
  while the dynamic ring glows and orbits around the cursor position.
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

class VorbiumRingParticles {
  static get inputProperties() {
    return [
      '--cursor-x', '--cursor-y',
      '--t',
      '--animation-tick',
      '--theme-color',
      '--particle-count',
      '--particle-rows',
      '--particle-size',
      '--ring-radius',
      '--ring-thickness',
      '--seed',
      '--particle-min-alpha',
      '--particle-max-alpha',
    ];
  }

  constructor() {
    this.getRandom = mulberry32(0);
    this._cachedSeed = -1;
  }

  getBezierValue(t, p0, p1, p2, p3) {
    var u = 1 - t, tt = t * t, uu = u * u, uuu = uu * u, ttt = tt * t;
    return (uuu * p0) + (3 * uu * t * p1) + (3 * u * tt * p2) + (ttt * p3);
  }

  solveBezierX(targetX, x1, x2) {
    var t = targetX;
    for (var i = 0; i < 8; i++) {
      var currentX = this.getBezierValue(t, 0, x1, x2, 1);
      var t2 = Math.min(1, t + 0.001);
      var delta = t2 - t || 0.001;
      var slope = (this.getBezierValue(t2, 0, x1, x2, 1) - currentX) / delta;
      if (slope === 0) break;
      t -= (currentX - targetX) / slope;
    }
    return Math.max(0, Math.min(1, t));
  }

  hash(n) {
    var x = Math.sin(n) * 43758.5453123;
    return x - Math.floor(x);
  }

  randomInt(min, max) {
    return Math.floor(this.getRandom() * (max - min + 1)) + min;
  }

  randomFloat(min, max) {
    return min + this.getRandom() * (max - min);
  }

  _num(v, fallback) {
    if (!v) return fallback;
    if (typeof CSSUnitValue !== 'undefined' && v instanceof CSSUnitValue) return v.value;
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

  _parseColorToRgb(color) {
    var s = String(color).trim();
    if (s.startsWith('#')) {
      var c = s.substring(1);
      if (c.length === 3) c = c[0] + c[0] + c[1] + c[1] + c[2] + c[2];
      var num = parseInt(c, 16);
      return [(num >> 16) & 255, (num >> 8) & 255, num & 255];
    }
    var m = s.match(/^rgba?\(([^)]+)\)$/i);
    if (m) {
      var parts = m[1].split(',').map(function(x) { return parseFloat(x.trim()); });
      if (parts.length >= 3 && parts.every(function(n) { return Number.isFinite(n); })) {
        return [parts[0], parts[1], parts[2]];
      }
    }
    return [79, 70, 229];
  }

  _ensureSeedConstants(seed) {
    if (this._cachedSeed === seed) return;
    this._cachedSeed = seed;
    this.getRandom = mulberry32(seed);

    this._w1Freq = this.randomInt(2, 6);
    this._w1Speed = this.randomInt(1, 2);
    this._w1Dir = this.hash(seed + 10) > 0.5 ? 1 : -1;
    this._w2Freq = this.randomInt(2, 7);
    this._w2Speed = 1;
    this._w2Dir = -this._w1Dir;
    this._rowTwistStrength = this.randomFloat(0.2, 0.6);
    this._amplitude = this.randomInt(10, 22);
  }

  paint(ctx, geom, props) {
    var w = geom.width;
    var h = geom.height;

    // Parse inputs
    var cursorNx = this._norm01(this._num(props.get('--cursor-x'), 0.5));
    var cursorNy = this._norm01(this._num(props.get('--cursor-y'), 0.5));
    var tRaw = this._num(props.get('--t'), 0);
    var animTick = this._num(props.get('--animation-tick'), 0);
    var themeColor = this._str(props.get('--theme-color'), '#4f46e5');
    var numParticles = this._num(props.get('--particle-count'), 120);
    var numRows = this._num(props.get('--particle-rows'), 28);
    var particleSize = this._num(props.get('--particle-size'), 2.8);
    var innerRadius = this._num(props.get('--ring-radius'), 0);
    var thickness = this._num(props.get('--ring-thickness'), 0);
    var seed = this._num(props.get('--seed'), 42);
    var minAlpha = this._num(props.get('--particle-min-alpha'), 0.08);
    var maxAlpha = this._num(props.get('--particle-max-alpha'), 0.95);

    // Dynamic defaults from viewport
    var minDim = Math.min(w, h);
    if (innerRadius <= 0) innerRadius = minDim * 0.18;
    if (thickness <= 0) thickness = minDim * 0.38;

    this._ensureSeedConstants(seed);

    // ===== STATIC RING: centered with gentle cursor drift =====
    // Ring center: mostly at viewport center, with subtle cursor influence (15% blend)
    var cx = w * (0.425 + cursorNx * 0.15);
    var cy = h * (0.425 + cursorNy * 0.15);

    // Cursor position in pixel space
    var cursorPx = cursorNx * w;
    var cursorPy = cursorNy * h;

    // Repulsion parameters for static ring
    var repulsionRadius = minDim * 0.2;
    var repulsionStrength = 70;

    // Time
    var t = animTick > 0 ? animTick * Math.PI * 2 : tRaw * 0.01;

    var outerRadius = innerRadius + thickness;
    var halfThick = thickness / 2;

    // Easing for edge fade
    var bx1 = 0.42, by1 = 0, bx2 = 1, by2 = 1;

    // Parse color
    var rgb = this._parseColorToRgb(themeColor);
    var cr = rgb[0], cg = rgb[1], cb = rgb[2];

    // ===== PASS 1: Draw the static ring (large, centered) =====
    for (var r = 0; r < numRows; r++) {
      var rowProgress = numRows > 1 ? r / (numRows - 1) : 0;
      var currentBaseRadius = innerRadius + (rowProgress * thickness);

      for (var i = 0; i < numParticles; i++) {
        var angle = (i / numParticles) * Math.PI * 2;

        // Wave physics
        var wave1 = Math.sin((angle * this._w1Freq) + (t * this._w1Speed * this._w1Dir));
        var wave2 = Math.sin((angle * this._w2Freq) + (t * this._w2Speed * this._w2Dir));
        var rowOffset = Math.sin((r * this._rowTwistStrength) + t);
        var waveHeight = wave1 + wave2 + rowOffset;

        // Depth-based opacity
        var normalized = (waveHeight + 3) / 6;
        normalized = Math.pow(Math.max(0, normalized), 1.5);
        var alpha = minAlpha + (normalized * (maxAlpha - minAlpha));

        // Position with wave distortion
        var distortion = waveHeight * this._amplitude;
        var finalRadius = currentBaseRadius + distortion;
        var x = cx + Math.cos(angle) * finalRadius;
        var y = cy + Math.sin(angle) * finalRadius;

        // Cursor repulsion on static ring particles
        var dx = x - cursorPx;
        var dy = y - cursorPy;
        var distToCursor = Math.sqrt(dx * dx + dy * dy);

        if (distToCursor < repulsionRadius && distToCursor > 0.1) {
          var falloff = 1 - (distToCursor / repulsionRadius);
          falloff = falloff * falloff * falloff;
          x += (dx / distToCursor) * repulsionStrength * falloff;
          y += (dy / distToCursor) * repulsionStrength * falloff;
          alpha = Math.min(1, alpha + falloff * 0.35);
        }

        // Dual edge fade
        var distFromInner = finalRadius - innerRadius;
        var distFromOuter = outerRadius - finalRadius;
        var closestEdgeDist = Math.min(distFromInner, distFromOuter);
        var visibility = closestEdgeDist / halfThick;
        if (visibility < 0) visibility = 0;
        if (visibility > 1) visibility = 1;

        var easeT = this.solveBezierX(visibility, bx1, bx2);
        var easedVisibility = this.getBezierValue(easeT, 0, by1, by2, 1);
        alpha = alpha * easedVisibility;

        if (alpha < 0) alpha = 0;
        if (alpha > 1) alpha = 1;

        // Dynamic size near cursor
        var drawSize = particleSize;
        if (distToCursor < repulsionRadius && distToCursor > 0.1) {
          var sizeFalloff = 1 - (distToCursor / repulsionRadius);
          drawSize = particleSize + sizeFalloff * particleSize * 1.0;
        }

        if (alpha > 0.01) {
          ctx.fillStyle = 'rgba(' + cr + ',' + cg + ',' + cb + ',' + alpha + ')';
          ctx.beginPath();
          ctx.arc(x, y, drawSize, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
    }

    // ===== PASS 2: Dynamic cursor orbit ring =====
    // A smaller, brighter ring centered on the cursor that rotates and pulses
    var orbitRadius = minDim * 0.06;
    var orbitThickness = minDim * 0.08;
    var orbitRows = 8;
    var orbitParticles = 60;
    var orbitSize = particleSize * 0.7;

    // Use a different seed offset for orbit wave constants
    var orbitW1Freq = 3;
    var orbitW2Freq = 5;
    var orbitAmplitude = 6;

    // Lighter/brighter color for orbit ring
    var orbitCr = Math.min(255, cr + 60);
    var orbitCg = Math.min(255, cg + 60);
    var orbitCb = Math.min(255, cb + 30);

    var orbitOuterRadius = orbitRadius + orbitThickness;
    var orbitHalfThick = orbitThickness / 2;

    // Distance from cursor to viewport center — controls orbit opacity
    // When cursor is at center, orbit is subtle; when moving, it glows
    var dxCenter = cursorPx - cx;
    var dyCenter = cursorPy - cy;
    var distFromCenter = Math.sqrt(dxCenter * dxCenter + dyCenter * dyCenter);
    var orbitIntensity = Math.min(1, distFromCenter / (minDim * 0.3));

    // Orbit ring rotation offset — spins opposite to main ring
    var orbitTimeOffset = t * 1.5;

    for (var or = 0; or < orbitRows; or++) {
      var oRowProgress = orbitRows > 1 ? or / (orbitRows - 1) : 0;
      var oBaseRadius = orbitRadius + (oRowProgress * orbitThickness);

      for (var oi = 0; oi < orbitParticles; oi++) {
        var oAngle = (oi / orbitParticles) * Math.PI * 2;

        // Orbit wave physics (faster, tighter)
        var oWave1 = Math.sin((oAngle * orbitW1Freq) + (orbitTimeOffset * 2));
        var oWave2 = Math.sin((oAngle * orbitW2Freq) - (orbitTimeOffset * 1.3));
        var oRowOff = Math.sin((or * 0.5) + orbitTimeOffset);
        var oWaveHeight = oWave1 + oWave2 + oRowOff;

        var oNorm = (oWaveHeight + 3) / 6;
        oNorm = Math.pow(Math.max(0, oNorm), 1.2);

        // Orbit alpha: brighter when cursor is moving away from center
        var oAlpha = 0.15 + (oNorm * 0.7 * orbitIntensity);

        var oDistortion = oWaveHeight * orbitAmplitude;
        var oFinalRadius = oBaseRadius + oDistortion;
        var ox = cursorPx + Math.cos(oAngle) * oFinalRadius;
        var oy = cursorPy + Math.sin(oAngle) * oFinalRadius;

        // Orbit edge fade
        var oDistInner = oFinalRadius - orbitRadius;
        var oDistOuter = orbitOuterRadius - oFinalRadius;
        var oClosest = Math.min(oDistInner, oDistOuter);
        var oVis = oClosest / orbitHalfThick;
        if (oVis < 0) oVis = 0;
        if (oVis > 1) oVis = 1;
        oAlpha = oAlpha * oVis;

        if (oAlpha < 0) oAlpha = 0;
        if (oAlpha > 1) oAlpha = 1;

        if (oAlpha > 0.01) {
          ctx.fillStyle = 'rgba(' + orbitCr + ',' + orbitCg + ',' + orbitCb + ',' + oAlpha + ')';
          ctx.beginPath();
          ctx.arc(ox, oy, orbitSize, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
    }
  }
}

registerPaint('verbium-particles', VorbiumRingParticles);
