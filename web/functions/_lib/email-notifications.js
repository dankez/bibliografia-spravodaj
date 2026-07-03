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

const DEFAULT_SMTP_HOST = 'smtp.m1.websupport.sk';
const DEFAULT_SMTP_PORT = 465;
const DEFAULT_HELO_DOMAIN = 'bibliografia.sss.sk';
const MIME_BOUNDARY = 'sss-bibliografia-errata-boundary';

function cleanText(value, maxLength = 500) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

function cleanMultiline(value, maxLength = 4000) {
  return String(value || '').replace(/\r\n/g, '\n').trim().slice(0, maxLength);
}

function parsePort(value, fallback = DEFAULT_SMTP_PORT) {
  const parsed = Number.parseInt(String(value || ''), 10);
  return Number.isFinite(parsed) && parsed > 0 && parsed < 65536 ? parsed : fallback;
}

function parseEmailList(value) {
  return String(value || '')
    .split(/[;,\n]/)
    .map((item) => extractEmailAddress(item))
    .filter(Boolean);
}

function extractEmailAddress(value) {
  const text = cleanText(value, 320);
  const angleMatch = /<([^<>]+)>/.exec(text);
  const candidate = angleMatch ? angleMatch[1].trim() : text;
  if (!/^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$/.test(candidate)) return '';
  return candidate;
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function absoluteUrl(value, fallbackOrigin = '') {
  const cleanValue = cleanText(value, 1000);
  if (!cleanValue) return '';
  try {
    return new URL(cleanValue, fallbackOrigin || undefined).href;
  } catch {
    return cleanValue;
  }
}

function issueNumberFromUrl(issueUrl) {
  const cleanUrl = cleanText(issueUrl, 1000);
  try {
    const url = new URL(cleanUrl);
    const match = /\/issues\/(\d+)\/?$/.exec(url.pathname);
    return match ? match[1] : '';
  } catch {
    const match = /\/issues\/(\d+)\/?$/.exec(cleanUrl);
    return match ? match[1] : '';
  }
}

function adminUrlForIssue(adminUrl, issueUrl) {
  const cleanAdminUrl = cleanText(adminUrl, 1000);
  const issueNumber = issueNumberFromUrl(issueUrl);
  if (!cleanAdminUrl || !issueNumber) return cleanAdminUrl;
  try {
    const url = new URL(cleanAdminUrl);
    url.searchParams.set('issue', issueNumber);
    return url.href;
  } catch {
    const separator = cleanAdminUrl.includes('?') ? '&' : '?';
    return `${cleanAdminUrl}${separator}issue=${encodeURIComponent(issueNumber)}`;
  }
}

function base64Utf8(value) {
  const bytes = new TextEncoder().encode(String(value || ''));
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function encodeHeaderValue(value) {
  const cleanValue = cleanText(value, 998).replace(/[\r\n]/g, ' ');
  if (/^[\x20-\x7E]*$/.test(cleanValue)) return cleanValue;
  return `=?UTF-8?B?${base64Utf8(cleanValue)}?=`;
}

function dotStuff(value) {
  return String(value || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .split('\n')
    .map((line) => (line.startsWith('.') ? `.${line}` : line))
    .join('\r\n');
}

function normalizeTransport(value, port) {
  const configured = cleanText(value, 20);
  if (['on', 'off', 'starttls'].includes(configured)) return configured;
  return port === 465 ? 'on' : 'starttls';
}

export function errataEmailConfig(env = {}) {
  const recipients = parseEmailList(env.ERRATA_EMAIL_TO);
  const from = cleanText(env.ERRATA_EMAIL_FROM, 320);
  const username = cleanText(env.ERRATA_SMTP_USERNAME, 320);
  const password = String(env.ERRATA_SMTP_PASSWORD || '');
  const envelopeFrom = extractEmailAddress(env.ERRATA_EMAIL_ENVELOPE_FROM || from);

  if (!recipients.length || !from || !envelopeFrom || !username || !password) return null;

  const port = parsePort(env.ERRATA_SMTP_PORT);
  return {
    from,
    envelopeFrom,
    recipients,
    replyTo: cleanText(env.ERRATA_EMAIL_REPLY_TO, 320),
    smtp: {
      host: cleanText(env.ERRATA_SMTP_HOST, 260) || DEFAULT_SMTP_HOST,
      port,
      username,
      password,
      secureTransport: normalizeTransport(env.ERRATA_SMTP_SECURE_TRANSPORT, port),
      heloDomain: cleanText(env.ERRATA_SMTP_HELO_DOMAIN, 120) || DEFAULT_HELO_DOMAIN,
    },
  };
}

export function buildErrataNotificationEmail({ data, issueUrl, adminUrl, origin = '' }) {
  const articleId = cleanText(data.articleId, 80);
  const typeLabel = TYPE_LABELS[data.type] || cleanText(data.type, 80) || 'Oprava';
  const title = cleanText(data.articleTitle || data.proposedArticle?.title, 260) || 'neuvedené';
  const changedFields = Array.isArray(data.changedFields) && data.changedFields.length ? data.changedFields.join(', ') : 'neuvedené';
  const articleUrl = absoluteUrl(data.articleUrl, origin);
  const sourceVersion = cleanText(data.sourceVersion, 160) || 'neuvedené';
  const contact = cleanText(data.email, 180) || 'neuvedený';
  const message = cleanMultiline(data.message);
  const subjectTarget = articleId ? `#${articleId}` : title;
  const subject = `[bibliografia] Nová oprava ${subjectTarget}: ${typeLabel}`;
  const targetedAdminUrl = adminUrlForIssue(absoluteUrl(adminUrl, origin), issueUrl);

  const textRows = [
    `Nová komunitná oprava: ${typeLabel}`,
    '',
    `Článok: ${articleId || 'neuvedené'}`,
    `Názov: ${title}`,
    `Zmenené polia: ${changedFields}`,
    `Release zdroja: ${sourceVersion}`,
    `Kontakt: ${contact}`,
    '',
    `GitHub issue: ${issueUrl || 'neuvedené'}`,
    `Admin kontrola: ${targetedAdminUrl || 'neuvedené'}`,
    articleUrl ? `Detail článku: ${articleUrl}` : '',
    '',
    'Poznámka používateľa:',
    message || 'neuvedené',
  ].filter((row) => row !== '');

  const html = `<!doctype html>
<html>
  <body style="font-family: Arial, sans-serif; color: #1f1b18; line-height: 1.5;">
    <h1 style="font-size: 20px; margin: 0 0 12px;">Nová komunitná oprava</h1>
    <p style="margin: 0 0 16px;">V digitálnej bibliografii pribudlo errata hlásenie na kontrolu.</p>
    <table cellpadding="6" cellspacing="0" style="border-collapse: collapse; border: 1px solid #d8d0c8;">
      <tr><th align="left">Typ</th><td>${escapeHtml(typeLabel)}</td></tr>
      <tr><th align="left">Článok</th><td>${escapeHtml(articleId || 'neuvedené')}</td></tr>
      <tr><th align="left">Názov</th><td>${escapeHtml(title)}</td></tr>
      <tr><th align="left">Zmenené polia</th><td>${escapeHtml(changedFields)}</td></tr>
      <tr><th align="left">Release</th><td>${escapeHtml(sourceVersion)}</td></tr>
      <tr><th align="left">Kontakt</th><td>${escapeHtml(contact)}</td></tr>
    </table>
    <p style="margin: 18px 0;">
      <a href="${escapeHtml(issueUrl)}" style="display: inline-block; padding: 10px 14px; background: #8f1f1f; color: #ffffff; text-decoration: none;">Otvoriť GitHub issue</a>
      <a href="${escapeHtml(targetedAdminUrl)}" style="display: inline-block; padding: 10px 14px; margin-left: 8px; border: 1px solid #8f1f1f; color: #8f1f1f; text-decoration: none;">Admin kontrola</a>
    </p>
    ${articleUrl ? `<p><a href="${escapeHtml(articleUrl)}">Detail článku</a></p>` : ''}
    <h2 style="font-size: 16px; margin: 20px 0 8px;">Poznámka používateľa</h2>
    <pre style="white-space: pre-wrap; background: #f6f1eb; padding: 12px; border: 1px solid #d8d0c8;">${escapeHtml(message || 'neuvedené')}</pre>
  </body>
</html>`;

  return {
    subject,
    text: textRows.join('\n'),
    html,
  };
}

function buildMimeMessage(config, message) {
  const toHeader = config.recipients.join(', ');
  const headers = [
    `From: ${config.from}`,
    `To: ${toHeader}`,
    config.replyTo ? `Reply-To: ${config.replyTo}` : '',
    `Subject: ${encodeHeaderValue(message.subject)}`,
    'MIME-Version: 1.0',
    `Content-Type: multipart/alternative; boundary="${MIME_BOUNDARY}"`,
  ].filter(Boolean);

  const body = [
    `--${MIME_BOUNDARY}`,
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: 8bit',
    '',
    message.text || '',
    `--${MIME_BOUNDARY}`,
    'Content-Type: text/html; charset=UTF-8',
    'Content-Transfer-Encoding: 8bit',
    '',
    message.html || '',
    `--${MIME_BOUNDARY}--`,
    '',
  ].join('\r\n');

  return `${headers.join('\r\n')}\r\n\r\n${body}`;
}

async function resolveConnect() {
  const sockets = await import('cloudflare:sockets');
  return sockets.connect;
}

class SmtpSocket {
  constructor(socket) {
    this.socket = socket;
    this.reader = socket.readable.getReader();
    this.writer = socket.writable.getWriter();
    this.decoder = new TextDecoder();
    this.encoder = new TextEncoder();
    this.buffer = '';
  }

  async write(value) {
    await this.writer.write(this.encoder.encode(value));
  }

  async readLine() {
    while (!this.buffer.includes('\n')) {
      const chunk = await this.reader.read();
      if (chunk.done) throw new Error('SMTP server zavrel spojenie bez úplnej odpovede.');
      this.buffer += this.decoder.decode(chunk.value, { stream: true });
    }
    const index = this.buffer.indexOf('\n');
    const line = this.buffer.slice(0, index).replace(/\r$/, '');
    this.buffer = this.buffer.slice(index + 1);
    return line;
  }

  async response() {
    const lines = [];
    while (true) {
      const line = await this.readLine();
      lines.push(line);
      if (/^\d{3} /.test(line)) {
        return { code: Number.parseInt(line.slice(0, 3), 10), lines };
      }
      if (!/^\d{3}-/.test(line)) throw new Error(`Neplatná SMTP odpoveď: ${line}`);
    }
  }

  async expect(expected, context) {
    const response = await this.response();
    const allowed = Array.isArray(expected) ? expected : [expected];
    if (!allowed.includes(response.code)) {
      throw new Error(`${context}: SMTP server vrátil ${response.code}: ${response.lines.join(' / ')}`);
    }
    return response;
  }

  async command(command, expected, context = command) {
    await this.write(`${command}\r\n`);
    return this.expect(expected, context);
  }

  async close() {
    try {
      this.reader.releaseLock();
    } catch {
      // ignore
    }
    try {
      await this.writer.close();
    } catch {
      // ignore
    }
    try {
      await this.socket.close?.();
    } catch {
      // ignore
    }
  }
}

export async function sendSmtpEmail(config, message, deps = {}) {
  const connect = deps.connect || (await resolveConnect());
  const socket = connect(
    { hostname: config.smtp.host, port: config.smtp.port },
    { secureTransport: config.smtp.secureTransport || 'on' }
  );
  await socket.opened;
  const smtp = new SmtpSocket(socket);
  const envelopeFrom = config.envelopeFrom || extractEmailAddress(config.from);
  const mimeMessage = dotStuff(buildMimeMessage(config, message));

  try {
    await smtp.expect(220, 'SMTP banner');
    await smtp.command(`EHLO ${config.smtp.heloDomain || DEFAULT_HELO_DOMAIN}`, 250, 'SMTP EHLO');
    await smtp.command('AUTH LOGIN', 334, 'SMTP AUTH LOGIN');
    await smtp.command(base64Utf8(config.smtp.username), 334, 'SMTP username');
    await smtp.command(base64Utf8(config.smtp.password), 235, 'SMTP password');
    await smtp.command(`MAIL FROM:<${envelopeFrom}>`, 250, 'SMTP MAIL FROM');
    for (const recipient of config.recipients) {
      await smtp.command(`RCPT TO:<${recipient}>`, [250, 251], `SMTP RCPT TO ${recipient}`);
    }
    await smtp.command('DATA', 354, 'SMTP DATA');
    await smtp.write(`${mimeMessage}\r\n.\r\n`);
    await smtp.expect(250, 'SMTP message body');
    await smtp.command('QUIT', 221, 'SMTP QUIT');
  } finally {
    await smtp.close();
  }

  return { ok: true, recipients: config.recipients };
}

export async function sendErrataNotification(env, data, request, issueUrl, deps = {}) {
  const config = errataEmailConfig(env);
  if (!config) return { ok: true, skipped: true, reason: 'Email not configured' };

  const origin = request ? new URL(request.url).origin : '';
  const adminUrl = cleanText(env.ERRATA_ADMIN_URL, 1000) || absoluteUrl('/admin/opravy/', origin);
  const email = buildErrataNotificationEmail({
    data,
    issueUrl,
    adminUrl,
    origin,
  });

  return sendSmtpEmail(config, email, deps);
}
