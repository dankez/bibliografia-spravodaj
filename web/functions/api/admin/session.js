import { authorizeAdmin } from '../../_lib/admin-auth.js';

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

export async function onRequestGet(context) {
  const auth = await authorizeAdmin(context.env, context.request);
  if (!auth.ok) return jsonResponse({ ok: false, error: auth.error }, auth.status);
  return jsonResponse({ ok: true, user: auth.user });
}

export async function onRequestOptions() {
  return jsonResponse({ ok: true });
}

export async function onRequest() {
  return jsonResponse({ ok: false, error: 'Použite GET.' }, 405);
}
