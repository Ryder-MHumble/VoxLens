$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$crawlerDir = Join-Path $repoRoot "packages\crawler"
$apiDir = Join-Path $repoRoot "apps\api"
$webDir = Join-Path $repoRoot "apps\web"

if (-not (Test-Path -LiteralPath (Join-Path $crawlerDir "main.py"))) {
  throw "VoxLens crawler package is missing. Expected packages\crawler\main.py."
}

Push-Location $repoRoot
uv sync --frozen
Pop-Location

Push-Location $crawlerDir
uv sync --frozen
Pop-Location

Push-Location $apiDir
uv sync --frozen
Pop-Location

Push-Location $webDir
pnpm install --frozen-lockfile
Pop-Location
