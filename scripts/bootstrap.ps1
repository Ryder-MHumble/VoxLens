$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$mediaCrawlerDir = Join-Path $repoRoot "external\MediaCrawler"
$backendDir = Join-Path $repoRoot "scancast"
$frontendDir = Join-Path $backendDir "frontend"

if (-not (Test-Path -LiteralPath (Join-Path $mediaCrawlerDir "main.py"))) {
  throw "MediaCrawler component is missing. Expected external\MediaCrawler\main.py."
}

Push-Location $mediaCrawlerDir
uv sync --frozen
Pop-Location

Push-Location $backendDir
uv sync --frozen
Pop-Location

Push-Location $frontendDir
pnpm install --frozen-lockfile
Pop-Location
