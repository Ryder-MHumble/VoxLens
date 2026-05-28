$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$rootPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$apiPython = Join-Path $repoRoot "apps\api\.venv\Scripts\python.exe"
$crawlerPython = Join-Path $repoRoot "packages\crawler\.venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $rootPython) -or -not (Test-Path -LiteralPath $apiPython) -or -not (Test-Path -LiteralPath $crawlerPython)) {
  throw "Missing local Python environments. Run .\scripts\bootstrap.ps1 first."
}

Write-Host "== Python syntax =="
& $rootPython -m compileall -q (Join-Path $repoRoot "packages\research_cli\voxlens_research")
& $apiPython -m compileall -q (Join-Path $repoRoot "apps\api\app")
& $crawlerPython -m compileall -q `
  (Join-Path $repoRoot "packages\crawler\config") `
  (Join-Path $repoRoot "packages\crawler\tools") `
  (Join-Path $repoRoot "packages\crawler\cmd_arg") `
  (Join-Path $repoRoot "packages\crawler\main.py")

Write-Host "== API platform catalog smoke =="
$env:PYTHONPATH = Join-Path $repoRoot "apps\api"
$apiSmoke = @'
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
'@
$apiSmoke | & $apiPython -

Write-Host "== CLI smoke =="
$env:PYTHONPATH = Join-Path $repoRoot "packages\research_cli"
& $rootPython -m voxlens_research.cli ffmpeg-check | Out-Null
$cliSmoke = @'
from voxlens_research.providers import crawler_provider, opencli_provider

assert opencli_provider.supports("youtube")
assert opencli_provider.supports("bilibili")
assert not opencli_provider.supports("xiaohongshu")
assert crawler_provider.supports("xiaohongshu")
print("ok")
'@
$cliSmoke | & $rootPython -

Write-Host "== Crawler wordcloud smoke =="
$env:PYTHONPATH = Join-Path $repoRoot "packages\crawler"
$crawlerSmoke = @'
from tools.words import AsyncWordCloudGenerator

generator = AsyncWordCloudGenerator()
assert isinstance(generator.stop_words, set)
print("ok")
'@
$crawlerSmoke | & $crawlerPython -

Write-Host "== Stale reference scan =="
$rg = Get-Command rg -ErrorAction SilentlyContinue
if ($rg) {
  $targets = @(
    (Join-Path $repoRoot "README.md"),
    (Join-Path $repoRoot "README.zh-CN.md"),
    (Join-Path $repoRoot "THIRD_PARTY_NOTICES.md"),
    (Join-Path $repoRoot "docs"),
    (Join-Path $repoRoot "apps\api"),
    (Join-Path $repoRoot "packages\research_cli"),
    (Join-Path $repoRoot "packages\crawler")
  )
  & rg -n "README_en|README_es|UPSTREAM_REVISION|api/webui|api/routers|docs/hit_stopwords|docs/STZHONGS|schema/tables\.sql" @targets
  if ($LASTEXITCODE -eq 0) {
    throw "Found stale references to removed standalone crawler assets."
  }
  if ($LASTEXITCODE -gt 1) {
    throw "Stale reference scan failed."
  }
} else {
  Write-Host "rg not found; skipped stale reference scan."
}

Write-Host "VoxLens runtime validation passed."
