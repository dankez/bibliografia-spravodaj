import { authorizeAdmin, sameOriginRequest } from '../../_lib/admin-auth.js';

const ARTICLE_EDIT_SCHEMA = 'sss-bibliografia/article-edit/v1';
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
  'pdf_url',
  'pdf_page_start',
  'pdf_page_end',
]);
const ARTICLE_DATA_PATHS = ['data/articles_with_urls.json', 'web/src/data/articles.json'];

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

function gitRefPath(refName) {
  return String(refName || '').split('/').map((part) => encodeURIComponent(part)).join('/');
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
    if (parsed?.schema !== ARTICLE_EDIT_SCHEMA) return null;
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
  if (field === 'has_map_plan') return value === true;
  if (['year', 'pdf_page_start', 'pdf_page_end'].includes(field)) {
    if (value === null || value === '') return null;
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (field === 'abstract') return String(value || '').replace(/\r\n/g, '\n').trim().slice(0, 2000);
  if (field === 'pdf_url') return cleanText(value, 800);
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

function issueSummary(issue) {
  const patch = normalizePatch(extractJsonPatch(issue.body));
  return {
    number: issue.number,
    title: issue.title || '',
    url: issue.html_url || '',
    author: issue.user?.login || '',
    created_at: issue.created_at || '',
    updated_at: issue.updated_at || '',
    labels: (issue.labels || []).map((label) => label.name).filter(Boolean),
    type: patch ? 'article_edit' : 'text',
    article_id: patch?.article_id || '',
    changed_fields: patch?.changed_fields || [],
    patch,
  };
}

function isErrataIssue(issue) {
  if (issue.pull_request) return false;
  const title = String(issue.title || '');
  const body = String(issue.body || '');
  return /^\[errata\]/i.test(title) || body.includes(ARTICLE_EDIT_SCHEMA);
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

function decodeBase64Utf8(content) {
  const binary = atob(String(content || '').replace(/\s+/g, ''));
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

async function getDefaultBranch(env) {
  const result = await githubFetch(env, '/repos/{repository}');
  if (!result.ok) throw new Error(result.data.message || 'Repository sa nepodarilo načítať.');
  return cleanText(result.data.default_branch, 100) || 'main';
}

async function getTextFile(env, path, ref) {
  const result = await githubFetch(env, `/repos/{repository}/contents/${encodeURIComponent(path).replace(/%2F/g, '/')}?ref=${encodeURIComponent(ref)}`);
  if (!result.ok) throw new Error(result.data.message || `Súbor ${path} sa nepodarilo načítať.`);
  return decodeBase64Utf8(result.data.content);
}

function articleComparableValue(article, field) {
  const defaults = {
    journal_id: 'spravodaj_sss',
    journal_title: 'Spravodaj Slovenskej speleologickej spoločnosti',
    journal_short_title: 'Spravodaj SSS',
  };
  return normalizePatchValue(field, Object.prototype.hasOwnProperty.call(article, field) ? article[field] : defaults[field]);
}

function sameValue(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function applyPatchToArticles(jsonText, patch, checkConflict = false) {
  const articles = JSON.parse(jsonText);
  if (!Array.isArray(articles)) throw new Error('Dátový súbor článkov nemá očakávaný formát.');
  const article = articles.find((item) => String(item.id) === String(patch.article_id));
  if (!article) throw new Error(`Článok #${patch.article_id} sa nenašiel v dátach.`);

  if (checkConflict) {
    const conflicting = patch.changed_fields.filter(
      (field) => !sameValue(articleComparableValue(article, field), patch.original[field])
    );
    if (conflicting.length) {
      const error = new Error(`Aktuálne dáta sa zmenili od nahlásenia. Konflikt: ${conflicting.join(', ')}`);
      error.status = 409;
      throw error;
    }
  }

  for (const field of patch.changed_fields) {
    article[field] = patch.proposed[field];
  }
  return `${JSON.stringify(articles, null, 2)}\n`;
}

async function getIssue(env, issueNumber) {
  const result = await githubFetch(env, `/repos/{repository}/issues/${issueNumber}`);
  if (!result.ok) throw new Error(result.data.message || 'Issue sa nepodarilo načítať.');
  return result.data;
}

async function createBlob(env, content) {
  const result = await githubFetch(env, '/repos/{repository}/git/blobs', {
    method: 'POST',
    body: JSON.stringify({ content, encoding: 'utf-8' }),
  });
  if (!result.ok) throw new Error(result.data.message || 'GitHub blob sa nepodarilo vytvoriť.');
  return result.data.sha;
}

async function approveIssueWithCommit(env, issue, patch) {
  const baseBranch = cleanText(env.ADMIN_BASE_BRANCH, 100) || (await getDefaultBranch(env));
  const baseRef = await githubFetch(env, `/repos/{repository}/git/ref/heads/${gitRefPath(baseBranch)}`);
  if (!baseRef.ok) throw new Error(baseRef.data.message || 'Base branch sa nepodarilo načítať.');
  const baseCommitSha = baseRef.data.object.sha;

  const baseCommit = await githubFetch(env, `/repos/{repository}/git/commits/${baseCommitSha}`);
  if (!baseCommit.ok) throw new Error(baseCommit.data.message || 'Base commit sa nepodarilo načítať.');

  const treeEntries = [];
  const updatedFiles = [];
  for (const path of ARTICLE_DATA_PATHS) {
    const current = await getTextFile(env, path, baseBranch);
    const updated = applyPatchToArticles(current, patch, path === 'web/src/data/articles.json');
    if (updated !== current) {
      const sha = await createBlob(env, updated);
      treeEntries.push({ path, mode: '100644', type: 'blob', sha });
      updatedFiles.push(path);
    }
  }
  if (!treeEntries.length) {
    const error = new Error('Navrhovaná oprava nemení aktuálne dátové súbory.');
    error.status = 409;
    throw error;
  }

  const tree = await githubFetch(env, '/repos/{repository}/git/trees', {
    method: 'POST',
    body: JSON.stringify({ base_tree: baseCommit.data.tree.sha, tree: treeEntries }),
  });
  if (!tree.ok) throw new Error(tree.data.message || 'GitHub tree sa nepodarilo vytvoriť.');

  const message = `Apply errata issue #${issue.number} for article #${patch.article_id}`;
  const commit = await githubFetch(env, '/repos/{repository}/git/commits', {
    method: 'POST',
    body: JSON.stringify({
      message,
      tree: tree.data.sha,
      parents: [baseCommitSha],
    }),
  });
  if (!commit.ok) throw new Error(commit.data.message || 'GitHub commit sa nepodarilo vytvoriť.');

  const updatedRef = await githubFetch(env, `/repos/{repository}/git/refs/heads/${gitRefPath(baseBranch)}`, {
    method: 'PATCH',
    body: JSON.stringify({ sha: commit.data.sha, force: false }),
  });
  if (!updatedRef.ok) throw new Error(updatedRef.data.message || 'GitHub branch sa nepodarilo aktualizovať.');

  const commitUrl = commit.data.html_url || `https://github.com/${repositoryName(env)}/commit/${commit.data.sha}`;
  const warnings = [];

  const comment = await githubFetch(env, `/repos/{repository}/issues/${issue.number}/comments`, {
    method: 'POST',
    body: JSON.stringify({
      body: [
        `Admin schválil návrh a zapísal opravu priamo do vetvy \`${baseBranch}\`.`,
        '',
        `- Článok: #${patch.article_id}`,
        `- Polia: ${patch.changed_fields.join(', ')}`,
        `- Súbory: ${updatedFiles.join(', ')}`,
        `- Commit: ${commitUrl}`,
      ].join('\n'),
    }),
  });
  if (!comment.ok) warnings.push(comment.data.message || 'Komentár do issue sa nepodarilo pridať.');

  const closedIssue = await githubFetch(env, `/repos/{repository}/issues/${issue.number}`, {
    method: 'PATCH',
    body: JSON.stringify({ state: 'closed', state_reason: 'completed' }),
  });
  if (!closedIssue.ok) warnings.push(closedIssue.data.message || 'Issue sa nepodarilo zavrieť.');

  return {
    commitUrl,
    commitSha: commit.data.sha,
    branch: baseBranch,
    files: updatedFiles,
    issueClosed: closedIssue.ok,
    commented: comment.ok,
    warnings,
  };
}

async function approveIssue(env, payload) {
  const issueNumber = Number.parseInt(String(payload.issueNumber || ''), 10);
  if (!Number.isFinite(issueNumber) || issueNumber <= 0) {
    return { ok: false, status: 400, error: 'Chýba platné číslo issue.' };
  }

  const issue = await getIssue(env, issueNumber);
  const patch = normalizePatch(extractJsonPatch(issue.body));
  if (!patch) {
    return { ok: false, status: 400, error: 'Issue neobsahuje platný JSON diff článku.' };
  }
  const approval = await approveIssueWithCommit(env, issue, patch);
  return { ok: true, issue: issueSummary(issue), approval };
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
    const result = await approveIssue(context.env, payload);
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
