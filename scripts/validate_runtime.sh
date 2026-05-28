#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

root_python="$repo_root/.venv/bin/python"
api_python="$repo_root/apps/api/.venv/bin/python"
crawler_python="$repo_root/packages/crawler/.venv/bin/python"

if [[ ! -x "$root_python" || ! -x "$api_python" || ! -x "$crawler_python" ]]; then
  echo "Missing local Python environments. Run ./scripts/bootstrap.sh first." >&2
  exit 1
fi

echo "== Python syntax =="
"$root_python" -m compileall -q "$repo_root/packages/research_cli/voxlens_research"
"$api_python" -m compileall -q "$repo_root/apps/api/app"
"$crawler_python" -m compileall -q \
  "$repo_root/packages/crawler/config" \
  "$repo_root/packages/crawler/tools" \
  "$repo_root/packages/crawler/cmd_arg" \
  "$repo_root/packages/crawler/main.py"

echo "== API platform catalog smoke =="
PYTHONPATH="$repo_root/apps/api" "$api_python" - <<'PY'
from app.capabilities import capabilities_payload
from app.main import app
from app.platform_catalog import CRAWLER_PLATFORM_CONFIG, CRAWLER_PLATFORM_IDS, DEFAULT_PLATFORM_IDS, public_platform_catalog

payload = capabilities_payload()
catalog = public_platform_catalog()
assert app.title == "VoxLens API"
assert set(DEFAULT_PLATFORM_IDS).issubset(catalog), "default platforms missing from public catalog"
assert set(CRAWLER_PLATFORM_CONFIG) == set(CRAWLER_PLATFORM_IDS), "crawler platform ids drifted from config"
assert payload["platformCatalog"] == catalog, "capabilities payload does not expose the shared platform catalog"
print("ok")
PY

echo "== CLI smoke =="
PYTHONPATH="$repo_root/packages/research_cli" "$root_python" -m voxlens_research.cli ffmpeg-check >/dev/null
PYTHONPATH="$repo_root/packages/research_cli" "$root_python" - <<'PY'
from voxlens_research.providers import crawler_provider, opencli_provider

assert opencli_provider.supports("youtube")
assert opencli_provider.supports("bilibili")
assert not opencli_provider.supports("xiaohongshu")
assert crawler_provider.supports("xiaohongshu")
print("ok")
PY

echo "== Crawler wordcloud smoke =="
PYTHONPATH="$repo_root/packages/crawler" "$crawler_python" - <<'PY'
from tools.words import AsyncWordCloudGenerator

generator = AsyncWordCloudGenerator()
assert isinstance(generator.stop_words, set)
print("ok")
PY

echo "== Stale reference scan =="
if command -v rg >/dev/null 2>&1; then
  if rg -n "README_en|README_es|UPSTREAM_REVISION|api/webui|api/routers|docs/hit_stopwords|docs/STZHONGS|schema/tables\\.sql" \
    "$repo_root/README.md" \
    "$repo_root/README.zh-CN.md" \
    "$repo_root/THIRD_PARTY_NOTICES.md" \
    "$repo_root/docs" \
    "$repo_root/apps/api" \
    "$repo_root/packages/research_cli" \
    "$repo_root/packages/crawler"; then
    echo "Found stale references to removed standalone crawler assets." >&2
    exit 1
  fi
else
  echo "rg not found; skipped stale reference scan."
fi

echo "VoxLens runtime validation passed."
