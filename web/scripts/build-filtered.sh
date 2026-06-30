#!/usr/bin/env bash
set -euo pipefail

export PUBLIC_RELEASE_SHA="${PUBLIC_RELEASE_SHA:-$(git rev-parse --short HEAD 2>/dev/null || echo local)}"
export PUBLIC_RELEASE_DATE="${PUBLIC_RELEASE_DATE:-$(date -u +%Y%m%d)}"
export NODE_OPTIONS="${NODE_OPTIONS:---max-old-space-size=2048}"

./node_modules/.bin/astro build 2>&1 | awk '
  /^[0-9][0-9]:[0-9][0-9]:[0-9][0-9][[:space:]]+├─/ {
    routes += 1
    printf "."
    if (routes % 100 == 0) {
      print " " routes
      fflush()
    }
    next
  }
  { print; fflush() }
'
