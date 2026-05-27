if (-not (Test-Path -LiteralPath "external\MediaCrawler\.git")) {
  New-Item -ItemType Directory -Force -Path external | Out-Null
  git clone --depth 1 https://github.com/NanmiCoder/MediaCrawler external/MediaCrawler
}
Push-Location external\MediaCrawler
uv sync
Pop-Location
uv sync
