import {
  adminSessionCookie,
  createAdminSession,
  expiredAdminSessionCookie,
  sameOriginRequest,
  verifyAdminPassword,
} from '../../_lib/admin-auth.js';

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

  let payload;
  try {
    payload = await context.request.json();
  } catch {
    return jsonResponse({ ok: false, error: 'Neplatný JSON.' }, 400);
  }

  const verified = await verifyAdminPassword(context.env, payload?.password || '');
  if (!verified.ok) {
    return jsonResponse(
      { ok: false, error: verified.error },
      verified.status || 401,
      { 'Set-Cookie': expiredAdminSessionCookie() }
    );
  }

  const session = await createAdminSession(context.env);
  if (!session.ok) return jsonResponse({ ok: false, error: session.error }, session.status || 503);

  return jsonResponse(
    { ok: true, user: session.user },
    200,
    { 'Set-Cookie': adminSessionCookie(session.token, session.maxAge) }
  );
}

export async function onRequestOptions() {
  return jsonResponse({ ok: true });
}

export async function onRequest() {
  return jsonResponse({ ok: false, error: 'Použite POST.' }, 405);
}
