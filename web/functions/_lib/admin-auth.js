export const ADMIN_SESSION_COOKIE = 'sss_admin_session';
const PASSWORD_HASH_ALGORITHM = 'sha256';
const LEGACY_PASSWORD_HASH_ALGORITHM = 'pbkdf2-sha256';
const DEFAULT_SESSION_SECONDS = 12 * 60 * 60;

function cleanText(value, maxLength = 500) {
  return String(value || '').replace(/\s+/g, ' ').trim().slice(0, maxLength);
}

function timingSafeEqual(left, right) {
  const a = String(left || '');
  const b = String(right || '');
  let diff = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    diff |= (a.charCodeAt(index) || 0) ^ (b.charCodeAt(index) || 0);
  }
  return diff === 0;
}

function timingSafeBytesEqual(left, right) {
  const a = left || new Uint8Array();
  const b = right || new Uint8Array();
  let diff = a.length ^ b.length;
  const length = Math.max(a.length, b.length);
  for (let index = 0; index < length; index += 1) {
    diff |= (a[index] || 0) ^ (b[index] || 0);
  }
  return diff === 0;
}

function base64UrlEncode(bytes) {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

function base64UrlDecode(value) {
  const normalized = String(value || '').replace(/-/g, '+').replace(/_/g, '/');
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=');
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

function jsonBase64UrlEncode(value) {
  return base64UrlEncode(new TextEncoder().encode(JSON.stringify(value)));
}

function jsonBase64UrlDecode(value) {
  return JSON.parse(new TextDecoder().decode(base64UrlDecode(value)));
}

function sessionSeconds(env) {
  const parsed = Number.parseInt(String(env.ADMIN_SESSION_SECONDS || ''), 10);
  if (Number.isFinite(parsed) && parsed >= 300 && parsed <= 7 * 24 * 60 * 60) return parsed;
  return DEFAULT_SESSION_SECONDS;
}

function sessionSecret(env) {
  return cleanText(env.SESSION_SECRET || env.ADMIN_SESSION_SECRET, 500);
}

function passwordHashSpec(env) {
  return cleanText(env.ADMIN_PASSWORD_HASH, 1200);
}

function parsePasswordHash(spec) {
  const parts = String(spec || '').split('$');
  if (parts.length === 3 && parts[0] === PASSWORD_HASH_ALGORITHM) {
    const salt = base64UrlDecode(parts[1]);
    const hash = base64UrlDecode(parts[2]);
    if (!salt.length || !hash.length) return null;
    return { algorithm: PASSWORD_HASH_ALGORITHM, salt, hash };
  }
  if (parts.length === 4 && parts[0] === LEGACY_PASSWORD_HASH_ALGORITHM) {
    return { algorithm: LEGACY_PASSWORD_HASH_ALGORITHM };
  }
  return null;
}

async function derivePasswordHash(password, salt) {
  const material = new Uint8Array([
    ...salt,
    ...new TextEncoder().encode(':'),
    ...new TextEncoder().encode(String(password || '')),
  ]);
  return new Uint8Array(await crypto.subtle.digest('SHA-256', material));
}

export async function verifyAdminPassword(env, password) {
  const hashSpec = passwordHashSpec(env);
  const parsed = parsePasswordHash(hashSpec);
  const missing = [];
  if (!hashSpec) missing.push('ADMIN_PASSWORD_HASH chýba');
  else if (!parsed) missing.push('ADMIN_PASSWORD_HASH má neplatný formát');
  else if (parsed.algorithm === LEGACY_PASSWORD_HASH_ALGORITHM) {
    missing.push('ADMIN_PASSWORD_HASH používa starý PBKDF2 formát, vygeneruj nový sha256 hash');
  }
  if (!sessionSecret(env)) missing.push('SESSION_SECRET chýba');
  if (missing.length) {
    return {
      ok: false,
      status: 503,
      error: `Admin login nie je nakonfigurovaný (${missing.join(', ')}).`,
    };
  }
  const derived = await derivePasswordHash(password, parsed.salt);
  if (!timingSafeBytesEqual(derived, parsed.hash)) {
    return { ok: false, status: 401, error: 'Neplatné heslo.' };
  }
  return { ok: true };
}

async function hmacSignature(secret, value) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(value));
  return base64UrlEncode(new Uint8Array(signature));
}

export async function createAdminSession(env) {
  const secret = sessionSecret(env);
  if (!secret) return { ok: false, status: 503, error: 'SESSION_SECRET nie je nakonfigurovaný.' };
  const now = Math.floor(Date.now() / 1000);
  const maxAge = sessionSeconds(env);
  const payload = {
    sub: cleanText(env.ADMIN_USER_LABEL || 'admin', 120) || 'admin',
    iat: now,
    exp: now + maxAge,
    nonce: crypto.randomUUID?.() || `${now}-${Math.random().toString(36).slice(2)}`,
  };
  const encodedPayload = jsonBase64UrlEncode(payload);
  const signature = await hmacSignature(secret, encodedPayload);
  return { ok: true, token: `${encodedPayload}.${signature}`, user: { email: payload.sub }, maxAge };
}

export async function verifyAdminSession(env, token) {
  const secret = sessionSecret(env);
  if (!secret) return { ok: false, status: 503, error: 'SESSION_SECRET nie je nakonfigurovaný.' };
  const parts = String(token || '').split('.');
  if (parts.length !== 2) return { ok: false, status: 401, error: 'Admin relácia nie je platná.' };
  const expectedSignature = await hmacSignature(secret, parts[0]);
  if (!timingSafeEqual(parts[1], expectedSignature)) {
    return { ok: false, status: 401, error: 'Admin relácia nie je platná.' };
  }
  try {
    const payload = jsonBase64UrlDecode(parts[0]);
    if (Number(payload.exp || 0) <= Math.floor(Date.now() / 1000)) {
      return { ok: false, status: 401, error: 'Admin relácia vypršala.' };
    }
    return { ok: true, user: { email: cleanText(payload.sub, 120) || 'admin' } };
  } catch {
    return { ok: false, status: 401, error: 'Admin relácia nie je platná.' };
  }
}

function requestCookie(request, name) {
  const cookieHeader = request.headers.get('Cookie') || '';
  for (const part of cookieHeader.split(';')) {
    const [rawName, ...rawValue] = part.trim().split('=');
    if (rawName === name) return rawValue.join('=');
  }
  return '';
}

export async function authorizeAdmin(env, request) {
  const token = requestCookie(request, ADMIN_SESSION_COOKIE);
  if (!token) return { ok: false, status: 401, error: 'Admin prihlásenie je vyžadované.' };
  return verifyAdminSession(env, token);
}

export function adminSessionCookie(token, maxAge) {
  return [
    `${ADMIN_SESSION_COOKIE}=${token}`,
    'Path=/',
    `Max-Age=${maxAge}`,
    'HttpOnly',
    'Secure',
    'SameSite=Strict',
  ].join('; ');
}

export function expiredAdminSessionCookie() {
  return [
    `${ADMIN_SESSION_COOKIE}=`,
    'Path=/',
    'Max-Age=0',
    'HttpOnly',
    'Secure',
    'SameSite=Strict',
  ].join('; ');
}

export function sameOriginRequest(request) {
  const origin = request.headers.get('Origin');
  if (!origin) return true;
  return origin === new URL(request.url).origin;
}
