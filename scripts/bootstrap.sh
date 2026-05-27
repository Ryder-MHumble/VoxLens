#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
media_crawler_dir="$repo_root/external/MediaCrawler"

if [[ ! -f "$media_crawler_dir/main.py" ]]; then
  echo "MediaCrawler component is missing. Expected external/MediaCrawler/main.py." >&2
  exit 1
fi

cd "$media_crawler_dir"
uv sync --frozen

cd "$repo_root/scancast"
uv sync --frozen

cd "$repo_root/scancast/frontend"
pnpm install --frozen-lockfile
