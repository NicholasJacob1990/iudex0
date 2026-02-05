import { NextRequest } from 'next/server';

export const runtime = 'nodejs';

// Same-origin proxy for the backend API.
// This avoids cross-origin redirects and ensures Authorization headers are preserved.
function getTargetBase(): string {
  // Points to backend root (without /api). Keep in sync with next.config.js default.
  // Use 127.0.0.1 by default to avoid localhost -> IPv6 (::1) resolution issues
  // when the backend is bound only on IPv4 (e.g. 0.0.0.0).
  return process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000';
}

function filterRequestHeaders(headers: Headers): Headers {
  const out = new Headers(headers);
  // These headers are either hop-by-hop or should be set by fetch automatically.
  out.delete('host');
  out.delete('connection');
  out.delete('content-length');
  out.delete('accept-encoding');
  // Force identity to avoid compressed bodies (proxy passes through raw bytes).
  out.set('accept-encoding', 'identity');
  return out;
}

function filterResponseHeaders(headers: Headers): Headers {
  const out = new Headers(headers);
  // Avoid sending compressed bodies we didn't negotiate.
  out.delete('content-encoding');
  // If chunked, the runtime will handle it.
  out.delete('transfer-encoding');
  return out;
}

function getProxyTimeoutMs(method: string, targetPath: string): number {
  const defaultMs = Number.parseInt(process.env.API_PROXY_TIMEOUT_MS || '300000', 10); // 5 min
  const longMs = Number.parseInt(process.env.API_PROXY_TIMEOUT_LONG_MS || '900000', 10); // 15 min
  const m = (method || '').toUpperCase();
  const p = String(targetPath || '').toLowerCase();

  // Long-running endpoints (LLM calls, exports, recomputes, large file uploads) can legitimately exceed 30s.
  const isLong =
    p.includes('transcription/apply-revisions')
    || p.includes('transcription/vomo/jobs')  // Large file uploads
    || p.includes('transcription/hearing/jobs')  // Large file uploads
    || p.includes('transcription/jobs') && (p.includes('recompute') || p.includes('export') || p.includes('quality'))
    || p.includes('quality/apply-unified-hil')
    || p.includes('quality/convert-to-hil')
    || p.includes('quality/validate')
    || p.includes('quality/analyze')
    || p.includes('quality/generate')
    || p.includes('advanced/audit-structure-rigorous')
    || p.includes('documents/export');

  if (isLong) return longMs;
  // Keep GETs bounded too, but allow POSTs a bit more by default.
  if (m === 'POST' || m === 'PUT') return defaultMs;
  return Math.min(defaultMs, 120000);
}

async function proxy(request: NextRequest, pathParts: string[]) {
  try {
    const targetBase = getTargetBase().replace(/\/+$/, '');
    const normalizedParts = Array.isArray(pathParts) ? pathParts : String(pathParts || '').split('/').filter(Boolean);
    const targetPath = normalizedParts.map(encodeURIComponent).join('/');
    // Backend exposes a root `/health` (no `/api` prefix) plus many `/api/*` routes.
    // Map `/api/health` -> `${targetBase}/health` for compatibility.
    const url =
      normalizedParts.length === 1 && normalizedParts[0] === 'health'
        ? new URL(`${targetBase}/health`)
        : new URL(`${targetBase}/api/${targetPath}`);
    // Preserve querystring
    request.nextUrl.searchParams.forEach((value, key) => {
      url.searchParams.append(key, value);
    });

    const method = request.method.toUpperCase();
    const headers = filterRequestHeaders(request.headers);

    const hasBody = method !== 'GET' && method !== 'HEAD';
    const contentLength = request.headers.get('content-length');
    const transferEncoding = request.headers.get('transfer-encoding');
    const hasData = hasBody && ((contentLength && parseInt(contentLength) > 0) || transferEncoding === 'chunked');

    const contentType = request.headers.get('content-type');
    console.log(`[Proxy] ${method} ${url.toString()} - Start`);
    console.log(`[Proxy] Content-Type: ${contentType}`);
    console.log(`[Proxy] Reading body? ${hasData} (CL: ${contentLength}, TE: ${transferEncoding})`);

    // Buffer once (keeps request retry-safe for redirects).
    let bodyBytes = null;
    if (hasData) {
      try {
        console.log('[Proxy] Awaiting arrayBuffer...');
        bodyBytes = new Uint8Array(await request.arrayBuffer());
        console.log(`[Proxy] Body read: ${bodyBytes.length} bytes`);
      } catch (e) {
        console.error('[Proxy] Error reading body:', e);
      }
    }

    const makeInit = (overrideMethod?: string): RequestInit => {
      const m = (overrideMethod || method).toUpperCase();
      const includeBody = m !== 'GET' && m !== 'HEAD';
      return {
        method: m,
        headers,
        // Avoid automatic redirect retries that can fail for buffered bodies.
        redirect: 'manual',
        // Note: do not set `duplex` here; Next's patched fetch can throw if an unsupported option is present.
        body: includeBody && bodyBytes ? Buffer.from(bodyBytes) : undefined,
        cache: 'no-store',
      };
    };

    console.log(`[Proxy] ${method} ${url.toString()} - Start`);
    const init = makeInit();
    console.log(`[Proxy] Init:`, JSON.stringify({ ...init, body: init.body ? '[Body]' : null }));

    // Add timeout to prevent indefinite hanging (configurable; some endpoints are long-running).
    const timeoutMs = getProxyTimeoutMs(method, normalizedParts.join('/'));
    const controller = timeoutMs > 0 ? new AbortController() : null;
    const id = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
    if (controller) init.signal = controller.signal;

    let res;
    try {
      const bodySize = bodyBytes ? bodyBytes.length : 0;
      console.log(`[Proxy] Sending ${method} to ${url.toString()} (body: ${bodySize} bytes, timeout: ${timeoutMs}ms)`);
      res = await fetch(url.toString(), init);
      console.log(`[Proxy] Response: ${res.status} ${res.statusText}`);
      // Follow a single redirect manually (common in FastAPI when trailing slashes differ).
      if ([301, 302, 303, 307, 308].includes(res.status)) {
        const loc = res.headers.get('location');
        if (loc) {
          const redirected = new URL(loc, url);
          // Per RFC, 303 should switch to GET
          const redirectedMethod = res.status === 303 ? 'GET' : method;
          const redirectedInit = makeInit(redirectedMethod);
          if (controller) redirectedInit.signal = controller.signal;
          res = await fetch(redirected.toString(), redirectedInit);
        }
      }
    } catch (e) {
      // Surface a clearer error when we abort locally.
      if ((e as any)?.name === 'AbortError') {
        throw new Error(`Proxy timeout after ${timeoutMs}ms for ${method} ${url.toString()}`);
      }
      throw e;
    } finally {
      if (id) clearTimeout(id);
    }
    const resHeaders = filterResponseHeaders(res.headers);
    // For SSE: disable buffering in common reverse proxies.
    if (resHeaders.get('content-type')?.includes('text/event-stream')) {
      resHeaders.set('cache-control', 'no-cache, no-transform');
      resHeaders.set('x-accel-buffering', 'no');
      resHeaders.set('connection', 'keep-alive');
    }

    // Stream through (works for SSE too).
    return new Response(res.body, {
      status: res.status,
      statusText: res.statusText,
      headers: resHeaders,
    });
  } catch (err) {
    console.error('API proxy error', err);
    return new Response(JSON.stringify({ error: 'API proxy error', detail: String((err as any)?.message || err) }), {
      status: 502,
      headers: { 'content-type': 'application/json' },
    });
  }
}

export async function GET(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path || []);
}
export async function POST(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path || []);
}
export async function PUT(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path || []);
}
export async function PATCH(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path || []);
}
export async function DELETE(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path || []);
}
export async function OPTIONS(request: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(request, params.path || []);
}
