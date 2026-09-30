#!/bin/bash
set -euo pipefail

if [ ! -d frontend/node_modules ]; then
  npm --prefix frontend install
fi

npm --prefix frontend run build

if [ ! -f .dev.vars ]; then
  cp .dev.vars.example .dev.vars
fi

uv run pywrangler d1 migrations apply DB --local --env development
uv run pywrangler dev --env development --port 8787 --ip 0.0.0.0
