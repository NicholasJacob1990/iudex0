const html = `<!doctype html>
<html lang="pt-BR">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Iudex Dev Reset</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 24px; }
      code { background: #f1f5f9; padding: 2px 6px; border-radius: 6px; }
      .card { max-width: 720px; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px; }
      .muted { color: #64748b; }
      button { padding: 10px 14px; border-radius: 10px; border: 1px solid #e2e8f0; background: #0f172a; color: white; cursor: pointer; }
      button:disabled { opacity: 0.6; cursor: default; }
      .ok { color: #047857; font-weight: 600; }
      .warn { color: #b45309; font-weight: 600; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Reset de cache (dev)</h1>
      <p class="muted">Use isto quando você atualizou o frontend mas o navegador continua mostrando UI antiga (Service Worker/cache preso).</p>
      <p><button id="run">Executar reset</button></p>
      <pre id="log" class="muted"></pre>
      <p class="muted">Depois do reset, recarregue <code>/ask</code> ou a página do chat.</p>
    </div>
    <script>
      const logEl = document.getElementById('log');
      const btn = document.getElementById('run');
      const log = (msg) => { logEl.textContent += msg + "\\n"; };

      async function run() {
        btn.disabled = true;
        try {
          log("1) Limpando caches...");
          if ('caches' in window) {
            const keys = await caches.keys();
            await Promise.all(keys.map((k) => caches.delete(k)));
            log("   - caches removidos: " + keys.length);
          } else {
            log("   - Cache API indisponível");
          }

          log("2) Desregistrando Service Workers...");
          if ('serviceWorker' in navigator) {
            const regs = await navigator.serviceWorker.getRegistrations();
            await Promise.all(regs.map((r) => r.unregister()));
            log("   - SW removidos: " + regs.length);
          } else {
            log("   - Service Worker API indisponível");
          }

          log("3) Finalizado. Faça hard refresh (Ctrl+Shift+R / Cmd+Shift+R).");
          logEl.className = "ok";
        } catch (e) {
          log("ERRO: " + (e && e.message ? e.message : String(e)));
          logEl.className = "warn";
        } finally {
          btn.disabled = false;
        }
      }

      btn.addEventListener('click', run);
    </script>
  </body>
</html>`;

export function GET(): Response {
  return new Response(html, {
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store, must-revalidate',
    },
  });
}

