/*
  Wave Field Worklet
  Horizontal flowing sine waves with interference patterns and cursor distortion.
  For customers/collaboration pages — dynamic, fluid motion.
*/

class WaveField {
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
    return [99, 102, 241];
  }

  paint(ctx, geom, props) {
    var w = geom.width;
    var h = geom.height;

    var cursorNx = this._norm01(this._num(props.get('--cursor-x'), 0.5));
    var cursorNy = this._norm01(this._num(props.get('--cursor-y'), 0.5));
    var tRaw = this._num(props.get('--t'), 0);
    var animTick = this._num(props.get('--animation-tick'), 0);
    var themeColor = this._str(props.get('--theme-color'), '#6366f1');
    var seed = this._num(props.get('--seed'), 55);

    var t = animTick > 0 ? animTick * Math.PI * 2 : tRaw * 0.006;

    var rgb = this._parseColor(themeColor);
    var cr = rgb[0], cg = rgb[1], cb = rgb[2];

    // Secondary + tertiary colors
    var cr2 = Math.min(255, cr + 50);
    var cg2 = Math.min(255, cg + 80);
    var cb2 = Math.max(0, cb - 30);

    var cr3 = Math.max(0, cr - 30);
    var cg3 = Math.min(255, cg + 20);
    var cb3 = Math.min(255, cb + 60);

    var cursorPx = cursorNx * w;
    var cursorPy = cursorNy * h;
    var cursorInfluence = Math.min(w, h) * 0.3;

    // Number of wave layers
    var numWaves = 7;
    var stepX = 3;

    for (var waveIdx = 0; waveIdx < numWaves; waveIdx++) {
      var waveY = h * (0.2 + (waveIdx / (numWaves - 1)) * 0.6);
      var freq = 0.003 + waveIdx * 0.001;
      var amp = 30 + waveIdx * 8;
      var speed = (0.5 + waveIdx * 0.15) * (waveIdx % 2 === 0 ? 1 : -1);
      var phase = seed + waveIdx * 1.7;

      // Wave color blend
      var waveBlend = waveIdx / (numWaves - 1);
      var wr, wg, wb;
      if (waveBlend < 0.5) {
        var m = waveBlend * 2;
        wr = Math.round(cr + (cr2 - cr) * m);
        wg = Math.round(cg + (cg2 - cg) * m);
        wb = Math.round(cb + (cb2 - cb) * m);
      } else {
        var m2 = (waveBlend - 0.5) * 2;
        wr = Math.round(cr2 + (cr3 - cr2) * m2);
        wg = Math.round(cg2 + (cg3 - cg2) * m2);
        wb = Math.round(cb2 + (cb3 - cb2) * m2);
      }

      ctx.beginPath();

      var firstY = null;
      for (var px = 0; px <= w; px += stepX) {
        var nx = px / w;

        // Main wave
        var y = waveY +
          Math.sin(px * freq + t * speed + phase) * amp +
          Math.sin(px * freq * 2.3 - t * speed * 0.7 + phase * 1.3) * (amp * 0.4) +
          Math.sin(px * freq * 0.5 + t * speed * 1.5) * (amp * 0.25);

        // Cursor distortion
        var dx = px - cursorPx;
        var dy = y - cursorPy;
        var dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < cursorInfluence) {
          var factor = (1 - dist / cursorInfluence);
          factor = factor * factor * factor;
          y += (cursorPy - y) * factor * 0.4;
        }

        if (firstY === null) {
          firstY = y;
          ctx.moveTo(px, y);
        } else {
          ctx.lineTo(px, y);
        }
      }

      // Wave stroke with varying thickness
      var baseAlpha = 0.06 + (1 - Math.abs(waveBlend - 0.5) * 2) * 0.06;
      ctx.strokeStyle = 'rgba(' + wr + ',' + wg + ',' + wb + ',' + baseAlpha + ')';
      ctx.lineWidth = 1.5 + (1 - Math.abs(waveBlend - 0.5) * 2) * 1;
      ctx.stroke();

      // Fill below wave with subtle gradient
      ctx.lineTo(w, h);
      ctx.lineTo(0, h);
      ctx.closePath();
      var fillAlpha = 0.012 + (1 - Math.abs(waveBlend - 0.5) * 2) * 0.008;
      ctx.fillStyle = 'rgba(' + wr + ',' + wg + ',' + wb + ',' + fillAlpha + ')';
      ctx.fill();
    }

    // Interference dots at wave crossings (sampled sparingly)
    var dotSpacing = 24;
    var dotCols = Math.ceil(w / dotSpacing);
    for (var dc = 0; dc < dotCols; dc++) {
      var dpx = dc * dotSpacing + dotSpacing * 0.5;
      var waveVals = [];
      for (var wi = 0; wi < numWaves; wi++) {
        var dWaveY = h * (0.2 + (wi / (numWaves - 1)) * 0.6);
        var dFreq = 0.003 + wi * 0.001;
        var dAmp = 30 + wi * 8;
        var dSpeed = (0.5 + wi * 0.15) * (wi % 2 === 0 ? 1 : -1);
        var dPhase = seed + wi * 1.7;
        var yVal = dWaveY +
          Math.sin(dpx * dFreq + t * dSpeed + dPhase) * dAmp +
          Math.sin(dpx * dFreq * 2.3 - t * dSpeed * 0.7 + dPhase * 1.3) * (dAmp * 0.4);
        waveVals.push(yVal);
      }

      // Find close pairs
      for (var wa = 0; wa < waveVals.length; wa++) {
        for (var wb2 = wa + 1; wb2 < waveVals.length; wb2++) {
          var gap = Math.abs(waveVals[wa] - waveVals[wb2]);
          if (gap < 15) {
            var midY = (waveVals[wa] + waveVals[wb2]) * 0.5;
            var dotAlpha = (1 - gap / 15) * 0.2;
            var dotR = 2 + (1 - gap / 15) * 2;
            ctx.fillStyle = 'rgba(' + cr + ',' + cg + ',' + cb + ',' + dotAlpha + ')';
            ctx.beginPath();
            ctx.arc(dpx, midY, dotR, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }
    }
  }
}

registerPaint('wave-field', WaveField);
