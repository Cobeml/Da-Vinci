import { NextRequest } from 'next/server';
export const dynamic = 'force-dynamic';
async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const base = process.env.DAVINCI_API_URL || 'http://127.0.0.1:8000';
  const url = new URL('/api/' + path.map(encodeURIComponent).join('/'), base);
  url.search = request.nextUrl.search;
  const headers = new Headers();
  for (const name of ['content-type', 'last-event-id']) {
    const value = request.headers.get(name); if (value) headers.set(name, value);
  }
  if (process.env.DAVINCI_API_TOKEN) headers.set('authorization', 'Bearer ' + process.env.DAVINCI_API_TOKEN);
  // Same-origin mutations only, including when this proxy holds a backend token.
  const origin = request.headers.get('origin');
  if (request.method !== 'GET' && origin && origin !== request.nextUrl.origin) {
    return Response.json({detail:'Unexpected request origin'}, {status:403});
  }
  try {
    const response = await fetch(url, { method: request.method, headers, cache:'no-store',
      body: request.method === 'GET' ? undefined : await request.arrayBuffer(), signal: request.signal });
    return new Response(response.body, { status: response.status, headers: response.headers });
  } catch {
    return Response.json({detail:'Python API is unavailable. Start scripts/dev.sh.'}, {status:503});
  }
}
export const GET = proxy;
export const POST = proxy;
