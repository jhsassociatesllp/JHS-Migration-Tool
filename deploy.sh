#!/usr/bin/env bash
# Pulls the latest commit for whatever branch this checkout is on and (re)builds the
# stack in place. Run from inside a checkout directory — e.g. ~/apps/migration-tool-production
# on the VM (on `main`).
#
# Used by .github/workflows/deploy-production.yml over SSH, and safe to run by hand for
# the same effect.
set -euo pipefail

if [ ! -f .env ]; then
  echo "No .env in $(pwd) — copy .env.example to .env and fill in real values first (see docs/DEPLOYMENT_BHARAT_CLOUD.md)." >&2
  exit 1
fi

git fetch origin
git reset --hard "origin/$(git rev-parse --abbrev-ref HEAD)"

docker compose up -d --build

# Drop images/layers no longer referenced by any container — keeps a long-lived VM from
# quietly filling its disk with every previous build.
docker image prune -f
