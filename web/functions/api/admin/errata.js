import { authorizeAdmin, sameOriginRequest } from '../../_lib/admin-auth.js';

const ARTICLE_EDIT_SCHEMA = 'sss-bibliografia/article-edit/v1';
const FULLTEXT_REVIEW_SCHEMA = 'sss-bibliografia/fulltext-review/v1';
const DEFAULT_APPROVAL_WORKFLOW = 'approve-errata.yml';
const ARTICLE_EDIT_FIELDS = new Set([
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
]);

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

function repositoryName(env) {
  const repository = cleanText(env.GITHUB_REPOSITORY, 180);
  if (!/^[\w.-]+\/[\w.-]+$/.test(repository)) return '';
  return repository;
}

async function githubFetch(env, path, options = {}) {
  const token = env.GITHUB_TOKEN;
  const repository = repositoryName(env);
  if (!token || !repository) {
    return { ok: false, status: 503, data: { message: 'GitHub token alebo repository nie je nakonfigurovaný.' } };
  }
  const response = await fetch(`https://api.github.com${path.replace('{repository}', repository)}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
      'User-Agent': 'sss-bibliografia-admin',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(options.headers || {}),
    },
  });
  const data = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, data };
}

function extractJsonPatch(issueBody) {
  const match = /```json\s*([\s\S]*?)```/i.exec(String(issueBody || ''));
  if (!match) return null;
  try {
    const parsed = JSON.parse(match[1]);
    if (![ARTICLE_EDIT_SCHEMA, FULLTEXT_REVIEW_SCHEMA].includes(parsed?.schema)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function normalizePatchValue(field, value) {
  if (['authors', 'tags', 'caves', 'groups'].includes(field)) {
    return Array.isArray(value)
      ? value.map((item) => cleanText(item, 160)).filter(Boolean).slice(0, 80)
      : [];
  }
  if (field === 'map_plan_pages') {
    return Array.isArray(value)
      ? value.map((item) => Number.parseInt(String(item), 10)).filter((item) => Number.isFinite(item)).slice(0, 80)
      : [];
  }
  if (field === 'wikidata') return Array.isArray(value) ? value.slice(0, 80) : [];
  if (['has_map_plan', 'caves_verified'].includes(field)) return value === true;
  if (['year', 'pdf_page_start', 'pdf_page_end', 'pdf_page_offset', 'map_plan_score'].includes(field)) {
    if (value === null || value === '') return null;
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (field === 'abstract') return String(value || '').replace(/\r\n/g, '\n').trim().slice(0, 2000);
  if (['pdf_url', 'cover_url'].includes(field)) return cleanText(value, 800);
  return cleanText(value, 500);
}

function normalizeArticlePatchObject(value) {
  const source = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
  const normalized = {};
  for (const field of ARTICLE_EDIT_FIELDS) {
    normalized[field] = normalizePatchValue(field, source[field]);
  }
  return normalized;
}

function normalizePatch(rawPatch) {
  if (!rawPatch || rawPatch.schema !== ARTICLE_EDIT_SCHEMA) return null;
  const changedFields = Array.isArray(rawPatch.changed_fields)
    ? rawPatch.changed_fields.map((field) => cleanText(field, 80)).filter((field) => ARTICLE_EDIT_FIELDS.has(field))
    : [];
  const uniqueFields = [...new Set(changedFields)];
  if (!uniqueFields.length) return null;
  const articleId = cleanText(rawPatch.article_id, 40);
  if (!/^\d+$/.test(articleId)) return null;
  return {
    schema: ARTICLE_EDIT_SCHEMA,
    article_id: articleId,
    source_version: cleanText(rawPatch.source_version, 120),
    changed_fields: uniqueFields,
    original: normalizeArticlePatchObject(rawPatch.original),
    proposed: normalizeArticlePatchObject(rawPatch.proposed),
  };
}

function normalizeFulltextReview(rawPatch) {
  if (!rawPatch || rawPatch.schema !== FULLTEXT_REVIEW_SCHEMA) return null;
  const decision = cleanText(rawPatch.decision, 40);
  if (!['ok', 'rejected', 'needs_fix'].includes(decision)) return null;
  const articleId = cleanText(rawPatch.article_id, 40);
  if (!/^\d+$/.test(articleId)) return null;
  const decisionKey = cleanText(rawPatch.decision_key, 180);
  if (!decisionKey) return null;
  return {
    schema: FULLTEXT_REVIEW_SCHEMA,
    decision,
    decision_key: decisionKey,
    article_id: articleId,
    article_title: cleanText(rawPatch.article_title, 260),
    article_url: cleanText(rawPatch.article_url, 500),
    year: cleanText(rawPatch.year, 40),
    pages: cleanText(rawPatch.pages, 80),
    primary_issue: cleanText(rawPatch.primary_issue, 120),
    primary_label: cleanText(rawPatch.primary_label, 180),
    issue_codes: Array.isArray(rawPatch.issue_codes) ? rawPatch.issue_codes.map((item) => cleanText(item, 120)).filter(Boolean).slice(0, 30) : [],
    issue_labels: Array.isArray(rawPatch.issue_labels) ? rawPatch.issue_labels.map((item) => cleanText(item, 180)).filter(Boolean).slice(0, 30) : [],
    issue_score: cleanText(rawPatch.issue_score, 40),
    text_status: cleanText(rawPatch.text_status, 120),
    text_source: cleanText(rawPatch.text_source, 120),
    text_chars: cleanText(rawPatch.text_chars, 40),
    words: cleanText(rawPatch.words, 40),
    recommended_action: cleanText(rawPatch.recommended_action, 500),
    pdf_url: cleanText(rawPatch.pdf_url, 800),
    source_generated_at: cleanText(rawPatch.source_generated_at, 120),
    source_version: cleanText(rawPatch.source_version, 120),
  };
}

function issueSummary(issue) {
  const rawPatch = extractJsonPatch(issue.body);
  const articlePatch = normalizePatch(rawPatch);
  const fulltextReview = normalizeFulltextReview(rawPatch);
  const patch = articlePatch || fulltextReview;
  return {
    number: issue.number,
    title: issue.title || '',
    url: issue.html_url || '',
    author: issue.user?.login || '',
    created_at: issue.created_at || '',
    updated_at: issue.updated_at || '',
    labels: (issue.labels || []).map((label) => label.name).filter(Boolean),
    type: articlePatch ? 'article_edit' : fulltextReview ? 'fulltext_review' : 'text',
    article_id: patch?.article_id || '',
    changed_fields: articlePatch?.changed_fields || (fulltextReview ? ['decision'] : []),
    patch,
  };
}

function isErrataIssue(issue) {
  if (issue.pull_request) return false;
  const title = String(issue.title || '');
  const body = String(issue.body || '');
  return /^\[errata\]/i.test(title) || body.includes(ARTICLE_EDIT_SCHEMA) || body.includes(FULLTEXT_REVIEW_SCHEMA);
}

async function listIssues(env) {
  const issues = [];
  for (let page = 1; page <= 5; page += 1) {
    const result = await githubFetch(env, `/repos/{repository}/issues?state=open&per_page=100&page=${page}`);
    if (!result.ok) {
      return { ok: false, status: result.status, error: result.data.message || 'GitHub issues sa nepodarilo načítať.' };
    }
    const pageIssues = Array.isArray(result.data) ? result.data : [];
    issues.push(...pageIssues.filter(isErrataIssue).map(issueSummary));
    if (pageIssues.length < 100) break;
  }
  issues.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
  return { ok: true, issues };
}

async function getDefaultBranch(env) {
  const result = await githubFetch(env, '/repos/{repository}');
  if (!result.ok) throw new Error(result.data.message || 'Repository sa nepodarilo načítať.');
  return cleanText(result.data.default_branch, 100) || 'main';
}

async function getIssue(env, issueNumber) {
  const result = await githubFetch(env, `/repos/{repository}/issues/${issueNumber}`);
  if (!result.ok) throw new Error(result.data.message || 'Issue sa nepodarilo načítať.');
  return result.data;
}

function workflowFile(env) {
  const configured = cleanText(env.ADMIN_APPROVAL_WORKFLOW, 160);
  return configured || DEFAULT_APPROVAL_WORKFLOW;
}

async function dispatchApprovalWorkflow(env, issue, patch) {
  const baseBranch = cleanText(env.ADMIN_BASE_BRANCH, 100) || (await getDefaultBranch(env));
  const workflow = workflowFile(env);
  const result = await githubFetch(
    env,
    `/repos/{repository}/actions/workflows/${encodeURIComponent(workflow)}/dispatches`,
    {
      method: 'POST',
      body: JSON.stringify({
        ref: baseBranch,
        inputs: {
          issue_number: String(issue.number),
        },
      }),
    }
  );
  if (!result.ok) {
    throw new Error(result.data.message || 'GitHub Actions workflow sa nepodarilo spustiť.');
  }
  return {
    queued: true,
    workflow,
    branch: baseBranch,
    workflowUrl: `https://github.com/${repositoryName(env)}/actions/workflows/${encodeURIComponent(workflow)}`,
    articleId: patch.article_id,
    changedFields: patch.changed_fields || [patch.decision || 'decision'],
  };
}

function issuePatch(issue) {
  const rawPatch = extractJsonPatch(issue.body);
  return normalizePatch(rawPatch) || normalizeFulltextReview(rawPatch);
}

async function approveIssue(env, payload) {
  const issueNumber = Number.parseInt(String(payload.issueNumber || ''), 10);
  if (!Number.isFinite(issueNumber) || issueNumber <= 0) {
    return { ok: false, status: 400, error: 'Chýba platné číslo issue.' };
  }

  const issue = await getIssue(env, issueNumber);
  const patch = issuePatch(issue);
  if (!patch) {
    return { ok: false, status: 400, error: 'Issue neobsahuje platný štruktúrovaný JSON diff alebo rozhodnutie.' };
  }
  const approval = await dispatchApprovalWorkflow(env, issue, patch);
  return { ok: true, issue: issueSummary(issue), approval };
}

async function rejectIssue(env, payload) {
  const issueNumber = Number.parseInt(String(payload.issueNumber || ''), 10);
  if (!Number.isFinite(issueNumber) || issueNumber <= 0) {
    return { ok: false, status: 400, error: 'Chýba platné číslo issue.' };
  }

  const issue = await getIssue(env, issueNumber);
  if (!isErrataIssue(issue)) {
    return { ok: false, status: 400, error: 'Issue nie je rozpoznané ako errata hlásenie.' };
  }

  const patch = issuePatch(issue);
  const reason = cleanText(payload.reason, 1200) || 'Návrh nebol potvrdený pri redakčnej kontrole.';
  const changedFields = patch?.changed_fields || [patch?.decision || 'neuvedené'];
  const body = [
    'Admin zamietol návrh cez webové rozhranie. Dáta neboli zmenené.',
    '',
    `- Článok: #${patch?.article_id || issueSummary(issue).article_id || 'neuvedené'}`,
    `- Zmena: ${changedFields.join(', ')}`,
    '',
    'Dôvod:',
    '',
    reason,
  ].join('\n');

  const comment = await githubFetch(env, `/repos/{repository}/issues/${issueNumber}/comments`, {
    method: 'POST',
    body: JSON.stringify({ body }),
  });
  if (!comment.ok) {
    return { ok: false, status: comment.status, error: comment.data.message || 'Komentár k zamietnutiu sa nepodarilo vytvoriť.' };
  }

  const closed = await githubFetch(env, `/repos/{repository}/issues/${issueNumber}`, {
    method: 'PATCH',
    body: JSON.stringify({ state: 'closed', state_reason: 'not_planned' }),
  });
  if (!closed.ok) {
    return { ok: false, status: closed.status, error: closed.data.message || 'Issue sa nepodarilo zavrieť.' };
  }

  return {
    ok: true,
    issue: issueSummary(closed.data),
    rejection: {
      closed: true,
      issueUrl: closed.data.html_url || issue.html_url || '',
      commentUrl: comment.data.html_url || '',
      stateReason: closed.data.state_reason || 'not_planned',
    },
  };
}

export async function onRequestGet(context) {
  const auth = await authorizeAdmin(context.env, context.request);
  if (!auth.ok) return jsonResponse({ ok: false, error: auth.error }, auth.status);

  const result = await listIssues(context.env);
  if (!result.ok) return jsonResponse({ ok: false, error: result.error }, result.status);
  return jsonResponse({ ok: true, user: auth.user, issues: result.issues });
}

export async function onRequestPost(context) {
  if (!sameOriginRequest(context.request)) {
    return jsonResponse({ ok: false, error: 'Neplatný pôvod požiadavky.' }, 403);
  }
  const auth = await authorizeAdmin(context.env, context.request);
  if (!auth.ok) return jsonResponse({ ok: false, error: auth.error }, auth.status);

  let payload;
  try {
    payload = await context.request.json();
  } catch {
    return jsonResponse({ ok: false, error: 'Neplatný JSON.' }, 400);
  }

  try {
    const action = cleanText(payload.action, 40) || 'approve';
    if (!['approve', 'reject'].includes(action)) {
      return jsonResponse({ ok: false, error: 'Neplatná admin akcia.' }, 400);
    }
    const result = action === 'reject' ? await rejectIssue(context.env, payload) : await approveIssue(context.env, payload);
    return jsonResponse({ ...result, user: auth.user }, result.ok ? 200 : result.status || 400);
  } catch (error) {
    return jsonResponse({ ok: false, error: error.message || 'Schválenie zlyhalo.' }, error.status || 502);
  }
}

export async function onRequestOptions() {
  return jsonResponse({ ok: true });
}

export async function onRequest() {
  return jsonResponse({ ok: false, error: 'Použite GET alebo POST.' }, 405);
}
