const ALLOWED_TYPES = new Set(['author', 'title', 'pages', 'pdf', 'map_plan', 'abstract', 'other']);

const TYPE_LABELS = {
  author: 'Autor',
  title: 'Názov',
  pages: 'Strany',
  pdf: 'PDF odkaz',
  map_plan: 'Mapa/plán',
  abstract: 'Anotácia',
  other: 'Iné',
};

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Cache-Control': 'no-store',
    },
  });
}

function cleanText(value, maxLength = 500) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

function cleanMultiline(value, maxLength = 4000) {
  return String(value || '').replace(/\r\n/g, '\n').trim().slice(0, maxLength);
}

function validatePayload(payload) {
  if (cleanText(payload.website)) {
    return { ok: false, status: 400, error: 'Neplatné hlásenie.' };
  }

  const type = cleanText(payload.type, 40);
  if (!ALLOWED_TYPES.has(type)) {
    return { ok: false, status: 400, error: 'Neplatný typ chyby.' };
  }

  const message = cleanMultiline(payload.message);
  if (message.length < 10) {
    return { ok: false, status: 400, error: 'Popis chyby je príliš krátky.' };
  }

  const email = cleanText(payload.email, 180);
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { ok: false, status: 400, error: 'Kontaktný email nemá platný formát.' };
  }

  return {
    ok: true,
    data: {
      type,
      message,
      email,
      articleId: cleanText(payload.articleId, 40),
      articleTitle: cleanText(payload.articleTitle, 260),
      articleUrl: cleanText(payload.articleUrl, 500),
      turnstileToken: cleanText(payload.turnstileToken, 3000),
    },
  };
}

async function verifyTurnstile(env, token, request) {
  if (!env.TURNSTILE_SECRET_KEY) {
    if (env.ERROR_REPORT_ALLOW_INSECURE === 'true') return { ok: true };
    return { ok: false, error: 'Antispam overenie nie je nakonfigurované.' };
  }
  if (!token) {
    return { ok: false, error: 'Chýba antispam overenie.' };
  }

  const form = new FormData();
  form.append('secret', env.TURNSTILE_SECRET_KEY);
  form.append('response', token);
  const remoteIp = request.headers.get('CF-Connecting-IP');
  if (remoteIp) form.append('remoteip', remoteIp);

  const response = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', {
    method: 'POST',
    body: form,
  });
  const result = await response.json().catch(() => ({}));
  return result.success ? { ok: true } : { ok: false, error: 'Antispam overenie zlyhalo.' };
}

function issueBody(data, request) {
  const rows = [
    'Používateľ nahlásil chybu v bibliografii Spravodaja SSS.',
    '',
    `- Typ chyby: ${TYPE_LABELS[data.type] || data.type}`,
    `- Článok ID: ${data.articleId || 'neuvedené'}`,
    `- Názov: ${data.articleTitle || 'neuvedené'}`,
    `- URL: ${data.articleUrl || request.headers.get('Referer') || 'neuvedené'}`,
    `- Kontakt: ${data.email || 'neuvedený'}`,
    '',
    'Popis:',
    '',
    data.message,
  ];
  return rows.join('\n');
}

async function createGithubIssue(env, data, request) {
  const token = env.GITHUB_TOKEN;
  const repository = env.GITHUB_REPOSITORY;
  if (!token || !repository) {
    return { ok: false, status: 503, error: 'Prijímanie opráv nie je nakonfigurované.' };
  }

  const titleTarget = data.articleId ? `#${data.articleId}` : data.articleTitle || 'bez čísla článku';
  const payload = {
    title: `[errata] ${TYPE_LABELS[data.type] || data.type}: ${titleTarget}`,
    body: issueBody(data, request),
  };

  const labels = cleanText(env.GITHUB_ISSUE_LABELS, 200)
    .split(',')
    .map((label) => label.trim())
    .filter(Boolean);
  if (labels.length) payload.labels = labels;

  const response = await fetch(`https://api.github.com/repos/${repository}/issues`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
      'User-Agent': 'sss-bibliografia-error-report',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    body: JSON.stringify(payload),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { ok: false, status: 502, error: result.message || 'GitHub issue sa nepodarilo vytvoriť.' };
  }
  return { ok: true, issueUrl: result.html_url };
}

export async function onRequestPost(context) {
  let payload;
  try {
    payload = await context.request.json();
  } catch {
    return jsonResponse({ ok: false, error: 'Neplatný JSON.' }, 400);
  }

  const validation = validatePayload(payload);
  if (!validation.ok) return jsonResponse({ ok: false, error: validation.error }, validation.status);

  const turnstile = await verifyTurnstile(context.env, validation.data.turnstileToken, context.request);
  if (!turnstile.ok) return jsonResponse({ ok: false, error: turnstile.error }, 403);

  const github = await createGithubIssue(context.env, validation.data, context.request);
  if (!github.ok) return jsonResponse({ ok: false, error: github.error }, github.status);

  return jsonResponse({ ok: true, issueUrl: github.issueUrl || '' });
}

export async function onRequestOptions() {
  return jsonResponse({ ok: true });
}

export async function onRequest() {
  return jsonResponse({ ok: false, error: 'Použite POST.' }, 405);
}
