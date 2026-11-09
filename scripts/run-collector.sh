#!/bin/bash
# Entry point for the launchd agent.
#
# launchd starts processes with a minimal environment — no PATH to Homebrew,
# no shell profile — so everything here is absolute. The API key is read from
# .env at run time rather than copied into the plist, keeping one source of
# truth for it and keeping it out of ~/Library.

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$REPO"

if [ ! -f .env ]; then
  echo "no .env in $REPO — copy .env.example and add your AISStream key" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [ -z "${AISSTREAM_API_KEY:-}" ]; then
  echo "AISSTREAM_API_KEY is empty in $REPO/.env" >&2
  exit 1
fi

exec /opt/homebrew/bin/uv run python -m clearway.ais.collector
