const ALLOWED_TYPES = new Set([
  'author',
  'title',
  'pages',
  'pdf',
  'fulltext',
  'map_plan',
  'smopaj_number',
  'abstract',
  'tags',
  'article_edit',
  'fulltext_review',
  'other',
]);
const FULLTEXT_REVIEW_SCHEMA = 'sss-bibliografia/fulltext-review/v1';
const ARTICLE_EDIT_FIELDS = [
  'title',
  'authors',
  'journal_id',
  'journal_title',
  'journal_short_title',
  'year',
  'volume',
  'issue',
  'pages',
  'abstract',
  'tags',
  'caves',
  'groups',
  'has_map_plan',
  'map_plan_pages',
  'map_plan_score',
  'pdf_url',
  'pdf_page_start',
  'pdf_page_end',
  'pdf_page_offset',
  'caves_verified',
  'wikidata',
  'cover_url',
];

const TYPE_LABELS = {
  author: 'Autor',
  title: 'Názov',
  pages: 'Strany',
  pdf: 'PDF odkaz',
  fulltext: 'Fulltext / OCR',
  map_plan: 'Mapa/plán',
  smopaj_number: 'Číslo jaskyne / SMOPaJ',
  abstract: 'Anotácia',
  tags: 'Tagy / lokality',
  article_edit: 'Editácia článku',
  fulltext_review: 'Kontrola fulltextu',
  other: 'Všetko / iné',
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

function parseJsonObject(value, fallback = {}) {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value;
  if (typeof value !== 'string') return fallback;
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function parseStringArray(value, maxItems = 40, maxItemLength = 160) {
  const source = Array.isArray(value)
    ? value
    : String(value || '')
        .split('\n')
        .flatMap((item) => item.split(';'));
  return source
    .map((item) => cleanText(item, maxItemLength))
    .filter(Boolean)
    .slice(0, maxItems);
}

function parseIntegerArray(value, maxItems = 80) {
  const source = Array.isArray(value)
    ? value
    : String(value || '')
        .split('\n')
        .flatMap((item) => item.split(/[;,]/));
  return source
    .map((item) => Number.parseInt(String(item || '').trim(), 10))
    .filter((item) => Number.isFinite(item))
    .slice(0, maxItems);
}

function parseJsonArray(value, maxItems = 80) {
  if (Array.isArray(value)) return value.slice(0, maxItems);
  if (typeof value !== 'string' || !value.trim()) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.slice(0, maxItems) : [];
  } catch {
    return [];
  }
}

function cleanArticlePatchValue(field, value) {
  if (['authors', 'tags', 'caves', 'groups'].includes(field)) return parseStringArray(value);
  if (field === 'map_plan_pages') return parseIntegerArray(value);
  if (field === 'wikidata') return parseJsonArray(value);
  if (['has_map_plan', 'caves_verified'].includes(field)) return value === true || value === 'true' || value === 'on' || value === '1';
  if (['year', 'pdf_page_start', 'pdf_page_end', 'pdf_page_offset', 'map_plan_score'].includes(field)) {
    const number = Number.parseInt(String(value || ''), 10);
    return Number.isFinite(number) ? number : null;
  }
  if (field === 'abstract') return cleanMultiline(value, 2000);
  if (['pdf_url', 'cover_url'].includes(field)) return cleanText(value, 800);
  return cleanText(value, 500);
}

function cleanArticlePatchObject(value) {
  const raw = parseJsonObject(value);
  return Object.fromEntries(
    ARTICLE_EDIT_FIELDS.map((field) => [field, cleanArticlePatchValue(field, raw[field])])
  );
}

function cleanFulltextReviewDecision(value) {
  const raw = parseJsonObject(value);
  const decision = cleanText(raw.decision, 40);
  const allowedDecisions = new Set(['ok', 'rejected', 'needs_fix']);
  return {
    schema: FULLTEXT_REVIEW_SCHEMA,
    decision: allowedDecisions.has(decision) ? decision : '',
    decision_key: cleanText(raw.decision_key, 180),
    article_id: cleanText(raw.article_id, 40),
    article_title: cleanText(raw.article_title, 260),
    article_url: cleanText(raw.article_url, 500),
    year: cleanText(raw.year, 40),
    pages: cleanText(raw.pages, 80),
    primary_issue: cleanText(raw.primary_issue, 120),
    primary_label: cleanText(raw.primary_label, 180),
    issue_codes: parseStringArray(raw.issue_codes, 30, 120),
    issue_labels: parseStringArray(raw.issue_labels, 30, 180),
    issue_score: cleanText(raw.issue_score, 40),
    text_status: cleanText(raw.text_status, 120),
    text_source: cleanText(raw.text_source, 120),
    text_chars: cleanText(raw.text_chars, 40),
    words: cleanText(raw.words, 40),
    recommended_action: cleanText(raw.recommended_action, 500),
    pdf_url: cleanText(raw.pdf_url, 800),
    source_generated_at: cleanText(raw.source_generated_at, 120),
    source_version: cleanText(raw.source_version, 120),
  };
}

function articleValuesEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function validateArticleEdit(payload, message) {
  const original = cleanArticlePatchObject(payload.originalArticle);
  const proposed = cleanArticlePatchObject(payload.proposedArticle);
  const changedFields = ARTICLE_EDIT_FIELDS.filter((field) => !articleValuesEqual(original[field], proposed[field]));

  if (!cleanText(payload.articleId, 40)) {
    return { ok: false, status: 400, error: 'Chýba číslo článku.' };
  }
  if (!changedFields.length) {
    return { ok: false, status: 400, error: 'Nie je vyplnená žiadna zmena článku.' };
  }
  if (message.length < 10) {
    return { ok: false, status: 400, error: 'Poznámka k oprave je povinná a musí mať aspoň 10 znakov.' };
  }
  if (proposed.year !== null && (proposed.year < 1800 || proposed.year > 2100)) {
    return { ok: false, status: 400, error: 'Rok článku je mimo povoleného rozsahu.' };
  }
  if (proposed.pdf_url && !/^https?:\/\/[^\s]+$/i.test(proposed.pdf_url)) {
    return { ok: false, status: 400, error: 'PDF URL nemá platný formát.' };
  }

  return { ok: true, original, proposed, changedFields };
}

function validateFulltextReview(payload, message) {
  const review = cleanFulltextReviewDecision(payload.fulltextReviewDecision);
  if (!review.article_id || !/^\d+$/.test(review.article_id)) {
    return { ok: false, status: 400, error: 'Chýba číslo článku pre kontrolu fulltextu.' };
  }
  if (!review.decision_key) {
    return { ok: false, status: 400, error: 'Chýba identifikátor incidentu.' };
  }
  if (!review.decision) {
    return { ok: false, status: 400, error: 'Chýba platné rozhodnutie kontroly.' };
  }
  if (message.length < 10) {
    return { ok: false, status: 400, error: 'Poznámka ku kontrole musí mať aspoň 10 znakov.' };
  }
  return { ok: true, review };
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
  if (type !== 'article_edit' && message.length < 10) {
    return { ok: false, status: 400, error: 'Popis chyby je príliš krátky.' };
  }

  const email = cleanText(payload.email, 180);
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { ok: false, status: 400, error: 'Kontaktný email nemá platný formát.' };
  }

  const smopajCaveNumber = cleanText(payload.smopajCaveNumber, 40);
  if (type === 'smopaj_number' && !/^\d+(?:\.\d+)?$/.test(smopajCaveNumber)) {
    return { ok: false, status: 400, error: 'Číslo jaskyne zo zoznamu SMOPaJ nemá platný formát.' };
  }

  const articleEdit = type === 'article_edit' ? validateArticleEdit(payload, message) : null;
  if (articleEdit && !articleEdit.ok) {
    return { ok: false, status: articleEdit.status, error: articleEdit.error };
  }
  const fulltextReview = type === 'fulltext_review' ? validateFulltextReview(payload, message) : null;
  if (fulltextReview && !fulltextReview.ok) {
    return { ok: false, status: fulltextReview.status, error: fulltextReview.error };
  }

  return {
    ok: true,
    data: {
      type,
      message,
      email,
      articleId: fulltextReview?.review.article_id || cleanText(payload.articleId, 40),
      articleTitle: fulltextReview?.review.article_title || cleanText(payload.articleTitle, 260),
      articleUrl: fulltextReview?.review.article_url || cleanText(payload.articleUrl, 500),
      caveName: cleanText(payload.caveName, 260),
      caveSlug: cleanText(payload.caveSlug, 160),
      smopajCaveNumber,
      smopajCaveSearch: cleanText(payload.smopajCaveSearch, 260),
      smopajCaveLabel: cleanText(payload.smopajCaveLabel, 500),
      sourceVersion: cleanText(payload.sourceVersion, 120),
      changedFields: articleEdit?.changedFields || [],
      originalArticle: articleEdit?.original || null,
      proposedArticle: articleEdit?.proposed || null,
      fulltextReviewDecision: fulltextReview?.review || null,
      turnstileToken: cleanText(payload.turnstileToken || payload['cf-turnstile-response'], 3000),
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
  if (data.type === 'article_edit') return articleEditIssueBody(data, request);
  if (data.type === 'fulltext_review') return fulltextReviewIssueBody(data, request);
  const rows = [
    'Používateľ nahlásil chybu v bibliografii Spravodaja SSS.',
    '',
    `- Typ chyby: ${TYPE_LABELS[data.type] || data.type}`,
    `- Článok ID: ${data.articleId || 'neuvedené'}`,
    `- Názov: ${data.articleTitle || 'neuvedené'}`,
    `- URL: ${data.articleUrl || request.headers.get('Referer') || 'neuvedené'}`,
    `- Karta jaskyne: ${data.caveName || 'neuvedené'}`,
    `- Slug jaskyne: ${data.caveSlug || 'neuvedené'}`,
    `- Návrh čísla jaskyne SMOPaJ: ${data.smopajCaveNumber || 'neuvedené'}`,
    `- Vybraná položka zo zoznamu: ${data.smopajCaveLabel || 'neuvedené'}`,
    `- Hľadaný text v zozname: ${data.smopajCaveSearch || 'neuvedené'}`,
    `- Kontakt: ${data.email || 'neuvedený'}`,
    '',
    'Popis:',
    '',
    data.message,
  ];
  return rows.join('\n');
}

function fulltextReviewIssueBody(data, request) {
  const review = {
    ...data.fulltextReviewDecision,
    schema: FULLTEXT_REVIEW_SCHEMA,
    source_version: data.sourceVersion || data.fulltextReviewDecision?.source_version || 'neuvedené',
  };
  const rows = [
    'Používateľ navrhol rozhodnutie ku kontrole fulltextového incidentu.',
    '',
    `- Typ chyby: ${TYPE_LABELS[data.type]}`,
    `- Článok ID: ${data.articleId || 'neuvedené'}`,
    `- Názov: ${data.articleTitle || 'neuvedené'}`,
    `- URL: ${data.articleUrl || request.headers.get('Referer') || 'neuvedené'}`,
    `- Rozhodnutie: ${review.decision || 'neuvedené'}`,
    `- Incident: ${review.decision_key || 'neuvedené'}`,
    `- Problém: ${review.primary_label || review.primary_issue || 'neuvedené'}`,
    `- Release zdroja: ${review.source_version || 'neuvedené'}`,
    `- Kontakt: ${data.email || 'neuvedený'}`,
    '',
    'Poznámka používateľa:',
    '',
    data.message,
    '',
    'JSON rozhodnutie na kontrolu:',
    '',
    '```json',
    JSON.stringify(review, null, 2),
    '```',
  ];
  return rows.join('\n');
}

function articleEditIssueBody(data, request) {
  const patch = {
    schema: 'sss-bibliografia/article-edit/v1',
    article_id: data.articleId,
    source_version: data.sourceVersion || 'neuvedené',
    changed_fields: data.changedFields,
    original: data.originalArticle,
    proposed: data.proposedArticle,
  };
  const rows = [
    'Používateľ navrhol štruktúrovanú opravu článku v digitálnej bibliografii.',
    '',
    `- Typ chyby: ${TYPE_LABELS[data.type]}`,
    `- Článok ID: ${data.articleId || 'neuvedené'}`,
    `- Názov: ${data.articleTitle || data.proposedArticle?.title || 'neuvedené'}`,
    `- URL: ${data.articleUrl || request.headers.get('Referer') || 'neuvedené'}`,
    `- Zmenené polia: ${data.changedFields.length ? data.changedFields.join(', ') : 'neuvedené'}`,
    `- Release zdroja: ${data.sourceVersion || 'neuvedené'}`,
    `- Kontakt: ${data.email || 'neuvedený'}`,
    '',
    'Poznámka používateľa:',
    '',
    data.message,
    '',
    'JSON diff na kontrolu:',
    '',
    '```json',
    JSON.stringify(patch, null, 2),
    '```',
  ];
  return rows.join('\n');
}

async function createGithubIssue(env, data, request) {
  const token = env.GITHUB_TOKEN;
  const repository = env.GITHUB_REPOSITORY;
  if (!token || !repository) {
    return { ok: false, status: 503, error: 'Prijímanie opráv nie je nakonfigurované.' };
  }

  const titleTarget =
    data.type === 'smopaj_number'
      ? `${data.caveName || data.caveSlug || 'karta jaskyne'} -> ${data.smopajCaveNumber}`
      : data.type === 'article_edit'
        ? `#${data.articleId}: ${data.changedFields.join(', ')}`
      : data.type === 'fulltext_review'
        ? `#${data.articleId}: ${data.fulltextReviewDecision?.decision || 'kontrola'}`
      : data.articleId
        ? `#${data.articleId}`
        : data.articleTitle || 'bez čísla článku';
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
