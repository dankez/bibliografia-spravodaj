#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env.cloudflare-mail}"

if [[ ! -f "$ENV_FILE" ]]; then
  cat >&2 <<EOF
Missing $ENV_FILE

Create it locally with:

CLOUDFLARE_API_TOKEN=...
CF_PAGES_PROJECT_NAME=...
ERRATA_SMTP_PASSWORD=...

Optional overrides:
ERRATA_EMAIL_TO=bibliografia@sss.sk
ERRATA_EMAIL_FROM=Digitalna bibliografia SSS <admin@sss.sk>
ERRATA_EMAIL_REPLY_TO=bibliografia@sss.sk
ERRATA_ADMIN_URL=https://bibliografia.sss.sk/admin/opravy/
ERRATA_SMTP_HOST=smtp.m1.websupport.sk
ERRATA_SMTP_PORT=465
ERRATA_SMTP_USERNAME=admin@sss.sk
ERRATA_SMTP_SECURE_TRANSPORT=on
ERRATA_SMTP_HELO_DOMAIN=bibliografia.sss.sk
EOF
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required}"
: "${CF_PAGES_PROJECT_NAME:?CF_PAGES_PROJECT_NAME is required}"
: "${ERRATA_SMTP_PASSWORD:?ERRATA_SMTP_PASSWORD is required}"

ERRATA_EMAIL_TO="${ERRATA_EMAIL_TO:-bibliografia@sss.sk}"
ERRATA_EMAIL_FROM="${ERRATA_EMAIL_FROM:-Digitalna bibliografia SSS <admin@sss.sk>}"
ERRATA_EMAIL_REPLY_TO="${ERRATA_EMAIL_REPLY_TO:-bibliografia@sss.sk}"
ERRATA_ADMIN_URL="${ERRATA_ADMIN_URL:-https://bibliografia.sss.sk/admin/opravy/}"
ERRATA_SMTP_HOST="${ERRATA_SMTP_HOST:-smtp.m1.websupport.sk}"
ERRATA_SMTP_PORT="${ERRATA_SMTP_PORT:-465}"
ERRATA_SMTP_USERNAME="${ERRATA_SMTP_USERNAME:-admin@sss.sk}"
ERRATA_SMTP_SECURE_TRANSPORT="${ERRATA_SMTP_SECURE_TRANSPORT:-on}"
ERRATA_SMTP_HELO_DOMAIN="${ERRATA_SMTP_HELO_DOMAIN:-bibliografia.sss.sk}"

put_secret() {
  local key="$1"
  local value="$2"
  printf '%s' "$value" | CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" \
    npx wrangler pages secret put "$key" --project-name "$CF_PAGES_PROJECT_NAME"
}

echo "Configuring Cloudflare Pages secrets for project: $CF_PAGES_PROJECT_NAME"
put_secret ERRATA_EMAIL_TO "$ERRATA_EMAIL_TO"
put_secret ERRATA_EMAIL_FROM "$ERRATA_EMAIL_FROM"
put_secret ERRATA_EMAIL_REPLY_TO "$ERRATA_EMAIL_REPLY_TO"
put_secret ERRATA_ADMIN_URL "$ERRATA_ADMIN_URL"
put_secret ERRATA_SMTP_HOST "$ERRATA_SMTP_HOST"
put_secret ERRATA_SMTP_PORT "$ERRATA_SMTP_PORT"
put_secret ERRATA_SMTP_USERNAME "$ERRATA_SMTP_USERNAME"
put_secret ERRATA_SMTP_PASSWORD "$ERRATA_SMTP_PASSWORD"
put_secret ERRATA_SMTP_SECURE_TRANSPORT "$ERRATA_SMTP_SECURE_TRANSPORT"
put_secret ERRATA_SMTP_HELO_DOMAIN "$ERRATA_SMTP_HELO_DOMAIN"
echo "Cloudflare errata email secrets configured."
