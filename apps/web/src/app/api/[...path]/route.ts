import { NextRequest } from 'next/server';

export const runtime = 'nodejs';

// Same-origin proxy for the backend API.
// This avoids cross-origin redirects and ensures Authorization headers are preserved.
function getTargetBase(): string {
  // Points to backend root (without /api). Keep in sync with next.config.js default.
  return process.env.API_PROXY_TARGET || 'http://localhost:8000';
}

function filterRequestHeaders(headers: Headers): Headers {
  const out = new Headers(headers);
  // These headers are either hop-by-hop or should be set by fetch automatically.
  out.delete('host');
  out.delete('connection');
  out.delete('content-length');
  out.delete('accept-encoding');
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

async function proxy(request: NextRequest, pathParts: string[]) {
  const targetBase = getTargetBase().replace(/\/+$/, '');
  const targetPath = pathParts.map(encodeURIComponent).join('/');
  const url = new URL(`${targetBase}/api/${targetPath}`);
  // Preserve querystring
  request.nextUrl.searchParams.forEach((value, key) => {
    url.searchParams.append(key, value);
  });

  const method = request.method.toUpperCase();
  const headers = filterRequestHeaders(request.headers);

  const init: RequestInit = {
    method,
    headers,
    // @ts-expect-error duplex is required by Node for streaming request bodies in some runtimes
    duplex: 'half',
    // Avoid automatic redirect retries that can fail for buffered bodies.
    redirect: 'manual',
  };

  const bodyBuf = (method !== 'GET' && method !== 'HEAD') ? await request.arrayBuffer() : null;
  if (method !== 'GET' && method !== 'HEAD') {
    init.body = bodyBuf as ArrayBuffer;
  }

  let res = await fetch(url.toString(), init);
  // Follow a single redirect manually (common in FastAPI when trailing slashes differ).
  if ([301, 302, 303, 307, 308].includes(res.status)) {
    const loc = res.headers.get('location');
    if (loc) {
      const redirected = new URL(loc, url);
      const redirectedInit: RequestInit = {
        ...init,
        // Per RFC, 303 should switch to GET
        method: res.status === 303 ? 'GET' : init.method,
        body: res.status === 303 ? undefined : (bodyBuf as ArrayBuffer | null),
      };
      res = await fetch(redirected.toString(), redirectedInit);
    }
  }
  const resHeaders = filterResponseHeaders(res.headers);

  // Stream through (works for SSE too).
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: resHeaders,
  });
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

