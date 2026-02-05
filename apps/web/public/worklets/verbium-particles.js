/*
  Vorbium Particles Worklet — Enhanced v2
  Dual ring with constellation connections, glow trails, and color pulse.
  Inspired by Antigravity's gravitational lens + particle interconnections.
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

    var minDim = Math.min(w, h);
    if (innerRadius <= 0) innerRadius = minDim * 0.18;
    if (thickness <= 0) thickness = minDim * 0.38;

    this._ensureSeedConstants(seed);

    var cx = w * (0.425 + cursorNx * 0.15);
    var cy = h * (0.425 + cursorNy * 0.15);

    var cursorPx = cursorNx * w;
    var cursorPy = cursorNy * h;

    var repulsionRadius = minDim * 0.22;
    var repulsionStrength = 80;

    var t = animTick > 0 ? animTick * Math.PI * 2 : tRaw * 0.01;

    var outerRadius = innerRadius + thickness;
    var halfThick = thickness / 2;

    var rgb = this._parseColorToRgb(themeColor);
    var cr = rgb[0], cg = rgb[1], cb = rgb[2];

    // Secondary color (shifted hue) for color pulse
    var cr2 = Math.min(255, cr + 80);
    var cg2 = Math.max(0, cg - 30);
    var cb2 = Math.min(255, cb + 40);

    // Color pulse factor (oscillates 0-1)
    var colorPulse = (Math.sin(t * 0.3) + 1) * 0.5;

    // Store particle positions for constellation connections
    var positions = [];
    var connectionThreshold = minDim * 0.06;

    // ===== PASS 1: Ambient glow behind ring =====
    var glowRadius = (innerRadius + outerRadius) * 0.5;
    var glowGrad = ctx.createRadialGradient(cx, cy, glowRadius * 0.3, cx, cy, glowRadius * 1.2);
    var glowAlpha = 0.04 + colorPulse * 0.02;
    var mr = Math.round(cr + (cr2 - cr) * colorPulse);
    var mg = Math.round(cg + (cg2 - cg) * colorPulse);
    var mb = Math.round(cb + (cb2 - cb) * colorPulse);
    glowGrad.addColorStop(0, 'rgba(' + mr + ',' + mg + ',' + mb + ',' + glowAlpha + ')');
    glowGrad.addColorStop(0.5, 'rgba(' + mr + ',' + mg + ',' + mb + ',' + (glowAlpha * 0.5) + ')');
    glowGrad.addColorStop(1, 'rgba(' + mr + ',' + mg + ',' + mb + ',0)');
    ctx.fillStyle = glowGrad;
    ctx.fillRect(0, 0, w, h);

    // ===== PASS 2: Cursor glow =====
    var cursorGlowRad = minDim * 0.15;
    var cursorGrad = ctx.createRadialGradient(cursorPx, cursorPy, 0, cursorPx, cursorPy, cursorGlowRad);
    cursorGrad.addColorStop(0, 'rgba(' + cr2 + ',' + cg2 + ',' + cb2 + ',0.08)');
    cursorGrad.addColorStop(0.4, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.03)');
    cursorGrad.addColorStop(1, 'rgba(' + cr + ',' + cg + ',' + cb + ',0)');
    ctx.fillStyle = cursorGrad;
    ctx.fillRect(0, 0, w, h);

    // ===== PASS 3: Draw the static ring =====
    // Only store a subset for constellation (every 3rd particle of outer rows)
    for (var r = 0; r < numRows; r++) {
      var rowProgress = numRows > 1 ? r / (numRows - 1) : 0;
      var currentBaseRadius = innerRadius + (rowProgress * thickness);

      for (var i = 0; i < numParticles; i++) {
        var angle = (i / numParticles) * Math.PI * 2;

        var wave1 = Math.sin((angle * this._w1Freq) + (t * this._w1Speed * this._w1Dir));
        var wave2 = Math.sin((angle * this._w2Freq) + (t * this._w2Speed * this._w2Dir));
        var rowOffset = Math.sin((r * this._rowTwistStrength) + t);
        var waveHeight = wave1 + wave2 + rowOffset;

        var normalized = (waveHeight + 3) / 6;
        normalized = Math.pow(Math.max(0, normalized), 1.5);
        var alpha = minAlpha + (normalized * (maxAlpha - minAlpha));

        var distortion = waveHeight * this._amplitude;
        var finalRadius = currentBaseRadius + distortion;
        var x = cx + Math.cos(angle) * finalRadius;
        var y = cy + Math.sin(angle) * finalRadius;

        // Cursor repulsion
        var dx = x - cursorPx;
        var dy = y - cursorPy;
        var distToCursor = Math.sqrt(dx * dx + dy * dy);

        if (distToCursor < repulsionRadius && distToCursor > 0.1) {
          var falloff = 1 - (distToCursor / repulsionRadius);
          falloff = falloff * falloff * falloff;
          x += (dx / distToCursor) * repulsionStrength * falloff;
          y += (dy / distToCursor) * repulsionStrength * falloff;
          alpha = Math.min(1, alpha + falloff * 0.4);
        }

        // Edge fade
        var distFromInner = finalRadius - innerRadius;
        var distFromOuter = outerRadius - finalRadius;
        var closestEdgeDist = Math.min(distFromInner, distFromOuter);
        var visibility = Math.max(0, Math.min(1, closestEdgeDist / halfThick));
        alpha = alpha * visibility;

        if (alpha < 0) alpha = 0;
        if (alpha > 1) alpha = 1;

        // Dynamic size near cursor
        var drawSize = particleSize;
        if (distToCursor < repulsionRadius && distToCursor > 0.1) {
          var sizeFalloff = 1 - (distToCursor / repulsionRadius);
          drawSize = particleSize + sizeFalloff * particleSize * 1.2;
        }

        // Color interpolation based on wave phase + cursor proximity
        var colorMix = colorPulse * normalized;
        if (distToCursor < repulsionRadius) {
          colorMix = Math.min(1, colorMix + (1 - distToCursor / repulsionRadius) * 0.5);
        }
        var pr = Math.round(cr + (cr2 - cr) * colorMix);
        var pg = Math.round(cg + (cg2 - cg) * colorMix);
        var pb = Math.round(cb + (cb2 - cb) * colorMix);

        if (alpha > 0.01) {
          ctx.fillStyle = 'rgba(' + pr + ',' + pg + ',' + pb + ',' + alpha + ')';
          ctx.beginPath();
          ctx.arc(x, y, drawSize, 0, 2 * Math.PI);
          ctx.fill();

          // Store for constellation (subset)
          if (alpha > 0.15 && i % 3 === 0 && r % 2 === 0) {
            positions.push(x, y, alpha);
          }
        }
      }
    }

    // ===== PASS 4: Constellation connections =====
    ctx.lineWidth = 0.5;
    var numPts = positions.length / 3;
    for (var a = 0; a < numPts; a++) {
      var ax = positions[a * 3];
      var ay = positions[a * 3 + 1];
      var aAlpha = positions[a * 3 + 2];

      // Only connect to nearby particles
      for (var b = a + 1; b < numPts; b++) {
        var bx = positions[b * 3];
        var by = positions[b * 3 + 1];
        var bAlpha = positions[b * 3 + 2];

        var ddx = ax - bx;
        var ddy = ay - by;
        var dist = Math.sqrt(ddx * ddx + ddy * ddy);

        if (dist < connectionThreshold) {
          var lineAlpha = (1 - dist / connectionThreshold) * Math.min(aAlpha, bAlpha) * 0.25;
          if (lineAlpha > 0.01) {
            ctx.strokeStyle = 'rgba(' + cr + ',' + cg + ',' + cb + ',' + lineAlpha + ')';
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(bx, by);
            ctx.stroke();
          }
        }
      }
    }

    // ===== PASS 5: Dynamic cursor orbit ring =====
    var orbitRadius = minDim * 0.05;
    var orbitThickness = minDim * 0.09;
    var orbitRows = 8;
    var orbitParticles = 60;
    var orbitSize = particleSize * 0.65;

    var orbitW1Freq = 3;
    var orbitW2Freq = 5;
    var orbitAmplitude = 7;

    var orbitCr = Math.min(255, cr + 70);
    var orbitCg = Math.min(255, cg + 70);
    var orbitCb = Math.min(255, cb + 40);

    var orbitOuterRadius = orbitRadius + orbitThickness;
    var orbitHalfThick = orbitThickness / 2;

    var dxCenter = cursorPx - cx;
    var dyCenter = cursorPy - cy;
    var distFromCenter = Math.sqrt(dxCenter * dxCenter + dyCenter * dyCenter);
    var orbitIntensity = Math.min(1, distFromCenter / (minDim * 0.3));

    var orbitTimeOffset = t * 1.5;

    // Orbit glow
    if (orbitIntensity > 0.1) {
      var oGlowRad = orbitOuterRadius * 1.5;
      var oGlow = ctx.createRadialGradient(cursorPx, cursorPy, 0, cursorPx, cursorPy, oGlowRad);
      oGlow.addColorStop(0, 'rgba(' + orbitCr + ',' + orbitCg + ',' + orbitCb + ',' + (0.06 * orbitIntensity) + ')');
      oGlow.addColorStop(1, 'rgba(' + orbitCr + ',' + orbitCg + ',' + orbitCb + ',0)');
      ctx.fillStyle = oGlow;
      ctx.beginPath();
      ctx.arc(cursorPx, cursorPy, oGlowRad, 0, Math.PI * 2);
      ctx.fill();
    }

    for (var or2 = 0; or2 < orbitRows; or2++) {
      var oRowProgress = orbitRows > 1 ? or2 / (orbitRows - 1) : 0;
      var oBaseRadius = orbitRadius + (oRowProgress * orbitThickness);

      for (var oi = 0; oi < orbitParticles; oi++) {
        var oAngle = (oi / orbitParticles) * Math.PI * 2;

        var oWave1 = Math.sin((oAngle * orbitW1Freq) + (orbitTimeOffset * 2));
        var oWave2 = Math.sin((oAngle * orbitW2Freq) - (orbitTimeOffset * 1.3));
        var oRowOff = Math.sin((or2 * 0.5) + orbitTimeOffset);
        var oWaveHeight = oWave1 + oWave2 + oRowOff;

        var oNorm = (oWaveHeight + 3) / 6;
        oNorm = Math.pow(Math.max(0, oNorm), 1.2);

        var oAlpha = 0.15 + (oNorm * 0.7 * orbitIntensity);

        var oDistortion = oWaveHeight * orbitAmplitude;
        var oFinalRadius = oBaseRadius + oDistortion;
        var ox = cursorPx + Math.cos(oAngle) * oFinalRadius;
        var oy = cursorPy + Math.sin(oAngle) * oFinalRadius;

        // Orbit edge fade
        var oDistInner = oFinalRadius - orbitRadius;
        var oDistOuter = orbitOuterRadius - oFinalRadius;
        var oClosest = Math.min(oDistInner, oDistOuter);
        var oVis = Math.max(0, Math.min(1, oClosest / orbitHalfThick));
        oAlpha = oAlpha * oVis;

        if (oAlpha < 0) oAlpha = 0;
        if (oAlpha > 1) oAlpha = 1;

        if (oAlpha > 0.01) {
          // Orbit particles also get color pulse
          var oColorMix = oNorm * 0.6;
          var opr = Math.round(orbitCr + (255 - orbitCr) * oColorMix * 0.3);
          var opg = Math.round(orbitCg + (255 - orbitCg) * oColorMix * 0.2);
          var opb = Math.round(orbitCb + (255 - orbitCb) * oColorMix * 0.1);

          ctx.fillStyle = 'rgba(' + opr + ',' + opg + ',' + opb + ',' + oAlpha + ')';
          ctx.beginPath();
          ctx.arc(ox, oy, orbitSize, 0, 2 * Math.PI);
          ctx.fill();
        }
      }
    }
  }
}

registerPaint('verbium-particles', VorbiumRingParticles);
