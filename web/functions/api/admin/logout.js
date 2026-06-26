import { expiredAdminSessionCookie, sameOriginRequest } from '../../_lib/admin-auth.js';

function jsonResponse(body, status = 200, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
      ...headers,
    },
  });
}

export async function onRequestPost(context) {
  if (!sameOriginRequest(context.request)) {
    return jsonResponse({ ok: false, error: 'Neplatný pôvod požiadavky.' }, 403);
  }
  return jsonResponse({ ok: true }, 200, { 'Set-Cookie': expiredAdminSessionCookie() });
}

export async function onRequestOptions() {
  return jsonResponse({ ok: true });
}

export async function onRequest() {
  return jsonResponse({ ok: false, error: 'Použite POST.' }, 405);
}
