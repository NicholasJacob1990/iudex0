/*
  Grid Pulse Worklet
  Dot grid with radial pulse from cursor and ambient wave animation.
  For auth pages — clean, geometric, techy feel.
*/

class GridPulse {
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
    var seed = this._num(props.get('--seed'), 33);

    var t = animTick > 0 ? animTick * Math.PI * 2 : tRaw * 0.008;

    var rgb = this._parseColor(themeColor);
    var cr = rgb[0], cg = rgb[1], cb = rgb[2];

    var cursorPx = cursorNx * w;
    var cursorPy = cursorNy * h;

    // Grid spacing
    var spacing = 32;
    var cols = Math.ceil(w / spacing) + 1;
    var rows = Math.ceil(h / spacing) + 1;
    var baseRadius = 1.2;
    var maxRadius = 3.5;

    // Pulse parameters
    var pulseRadius = Math.min(w, h) * 0.35;
    var waveSpeed = 2.5;
    var waveWidth = Math.min(w, h) * 0.12;

    // Ambient wave that travels across the grid
    var ambientWaveAngle = t * 0.2 + seed;
    var ambientWaveDirX = Math.cos(ambientWaveAngle);
    var ambientWaveDirY = Math.sin(ambientWaveAngle);

    for (var gy = 0; gy < rows; gy++) {
      for (var gx = 0; gx < cols; gx++) {
        var px = gx * spacing;
        var py = gy * spacing;

        // Distance to cursor
        var dx = px - cursorPx;
        var dy = py - cursorPy;
        var dist = Math.sqrt(dx * dx + dy * dy);

        // Cursor pulse: expanding ring
        var pulsePhase = dist - t * pulseRadius * waveSpeed;
        var pulseFactor = Math.exp(-Math.abs(pulsePhase % (pulseRadius * 2)) / waveWidth);

        // Cursor proximity glow
        var proximityFactor = 0;
        if (dist < pulseRadius) {
          proximityFactor = (1 - dist / pulseRadius);
          proximityFactor = proximityFactor * proximityFactor;
        }

        // Ambient wave
        var dotProduct = (px * ambientWaveDirX + py * ambientWaveDirY);
        var ambientPhase = Math.sin(dotProduct * 0.015 + t * 1.5);
        var ambientFactor = (ambientPhase + 1) * 0.5;

        // Combined size
        var sizeFactor = 0.3 + ambientFactor * 0.4 + pulseFactor * 0.6 + proximityFactor * 0.8;
        var dotRadius = baseRadius + (maxRadius - baseRadius) * Math.min(1, sizeFactor);

        // Alpha
        var alpha = 0.06 + ambientFactor * 0.08 + pulseFactor * 0.3 + proximityFactor * 0.4;
        if (alpha > 0.6) alpha = 0.6;

        // Color shift near cursor
        var colorShift = proximityFactor + pulseFactor * 0.5;
        var dr = Math.round(cr + (255 - cr) * colorShift * 0.3);
        var dg = Math.round(cg + (255 - cg) * colorShift * 0.2);
        var db = Math.round(cb + (255 - cb) * colorShift * 0.15);

        if (alpha > 0.02) {
          ctx.fillStyle = 'rgba(' + dr + ',' + dg + ',' + db + ',' + alpha + ')';
          ctx.beginPath();
          ctx.arc(px, py, dotRadius, 0, Math.PI * 2);
          ctx.fill();
        }

        // Connection lines to neighbors near cursor
        if (proximityFactor > 0.2 && gx < cols - 1 && gy < rows - 1) {
          var lineAlpha = proximityFactor * 0.12;
          ctx.strokeStyle = 'rgba(' + cr + ',' + cg + ',' + cb + ',' + lineAlpha + ')';
          ctx.lineWidth = 0.5;

          // Right neighbor
          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(px + spacing, py);
          ctx.stroke();

          // Bottom neighbor
          ctx.beginPath();
          ctx.moveTo(px, py);
          ctx.lineTo(px, py + spacing);
          ctx.stroke();
        }
      }
    }

    // Cursor glow overlay
    var glowR = pulseRadius * 0.6;
    var glow = ctx.createRadialGradient(cursorPx, cursorPy, 0, cursorPx, cursorPy, glowR);
    glow.addColorStop(0, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.06)');
    glow.addColorStop(0.5, 'rgba(' + cr + ',' + cg + ',' + cb + ',0.02)');
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);
  }
}

registerPaint('grid-pulse', GridPulse);
