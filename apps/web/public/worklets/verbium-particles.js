/*
  Vorbium Particles Worklet (Legal Graph Edition)
  Based on Antigravity/Bramus recipe.
  Draws a dynamic graph of "legal nodes" that connect and react to the cursor.
*/

registerPaint("verbium-particles", class {
    static get inputProperties() {
        return [
            "--cursor-x", "--cursor-y",   // 0..1
            "--t",                        // continuously increasing number
            "--theme-color",              // primary color
            "--particle-count"            // density
        ];
    }

    paint(ctx, geom, props) {
        const w = geom.width;
        const h = geom.height;

        // Parse inputs with defaults
        const cxN = this._num(props.get("--cursor-x"), 0.5);
        const cyN = this._num(props.get("--cursor-y"), 0.5);
        const t = this._num(props.get("--t"), 0);
        const count = this._num(props.get("--particle-count"), 60);
        const themeColorStr = this._str(props.get("--theme-color"), "#4f46e5");

        const cursorX = cxN * w;
        const cursorY = cyN * h;

        // Use a fixed seed-like approach for stable particles
        // We want them to drift slowly, not jitter randomly every frame
        const nodes = [];
        for (let i = 0; i < count; i++) {
            // Deterministic Pseudo-random positions based on index
            // This ensures they are "stable" across paints but distributed
            const seed = (i * 13371) % 100000 / 100000;

            // Add slow drift based on time
            // x/y are normalized 0-1
            const driftX = Math.sin(t * 0.0002 + i) * 0.1;
            const driftY = Math.cos(t * 0.0003 + i * 2) * 0.1;

            let x = (seed + driftX) % 1;
            let y = ((seed * 17 % 1) + driftY) % 1;

            // Wrap around
            if (x < 0) x += 1;
            if (y < 0) y += 1;

            nodes.push({
                x: x * w,
                y: y * h,
                id: i
            });
        }

        // Draw Connections (Graph Edges)
        // Only connect if close enough
        const connectionDist = 120;
        const cursorInteractionDist = 250;

        ctx.lineWidth = 1;

        // Optimization: Don't check every pair O(N^2), just N * small_k near neighbors?
        // For N=60-80, O(N^2) is fine (3600 checks).

        for (let i = 0; i < nodes.length; i++) {
            const node = nodes[i];

            // Interaction with cursor (Magnetic pull)
            const dxC = cursorX - node.x;
            const dyC = cursorY - node.y;
            const distC = Math.sqrt(dxC * dxC + dyC * dyC);

            let visualX = node.x;
            let visualY = node.y;

            if (distC < cursorInteractionDist) {
                // Pull towards cursor slightly
                const pull = (1 - distC / cursorInteractionDist) * 30;
                visualX += (dxC / distC) * pull;
                visualY += (dyC / distC) * pull;
            }

            // Draw Node
            const size = (i % 3 === 0) ? 2.5 : 1.5; // Some larger "key" nodes
            ctx.fillStyle = this._withAlpha(themeColorStr, 0.4);
            ctx.beginPath();
            ctx.arc(visualX, visualY, size, 0, Math.PI * 2);
            ctx.fill();

            // Check connections
            for (let j = i + 1; j < nodes.length; j++) {
                const other = nodes[j];
                // Roughly approximate other's visual pos (ignoring cursor pull for simple edges optimization)
                const dx = visualX - other.x;
                const dy = visualY - other.y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < connectionDist) {
                    const opacity = (1 - dist / connectionDist) * 0.15;
                    ctx.strokeStyle = this._withAlpha(themeColorStr, opacity);
                    ctx.beginPath();
                    ctx.moveTo(visualX, visualY);
                    ctx.lineTo(other.x, other.y);
                    ctx.stroke();
                }
            }

            // Connect to cursor if very close
            if (distC < 100) {
                const opacity = (1 - distC / 100) * 0.3;
                ctx.strokeStyle = this._withAlpha(themeColorStr, opacity);
                ctx.beginPath();
                ctx.moveTo(visualX, visualY);
                ctx.lineTo(cursorX, cursorY);
                ctx.stroke();
            }
        }
    }

    // Helpers from Recipe
    _num(v, fallback) {
        if (!v) return fallback;
        const s = v.toString().trim();
        const n = parseFloat(s);
        return Number.isFinite(n) ? n : fallback;
    }

    _str(v, fallback) {
        if (!v) return fallback;
        const s = v.toString().trim();
        return s.length ? s : fallback;
    }

    _withAlpha(color, alpha) {
        // Basic hex support for simple override or just return rgba constructed
        // Assuming input is hex or valid color string. 
        // If it is hex like #4f46e5, we need to convert to rgba to add alpha
        if (color.startsWith('#')) {
            let c = color.substring(1);
            if (c.length === 3) c = [c[0], c[0], c[1], c[1], c[2], c[2]].join('');
            const num = parseInt(c, 16);
            const r = (num >> 16) & 255;
            const g = (num >> 8) & 255;
            const b = num & 255;
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        }
        return color; // Fallback for named colors or already rgba
    }
});
