#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
crawler_dir="$repo_root/packages/crawler"
api_dir="$repo_root/apps/api"
web_dir="$repo_root/apps/web"

if [[ ! -f "$crawler_dir/main.py" ]]; then
  echo "VoxLens crawler package is missing. Expected packages/crawler/main.py." >&2
  exit 1
fi

cd "$repo_root"
uv sync --frozen

cd "$crawler_dir"
uv sync --frozen

cd "$api_dir"
uv sync --frozen

cd "$web_dir"
pnpm install --frozen-lockfile
