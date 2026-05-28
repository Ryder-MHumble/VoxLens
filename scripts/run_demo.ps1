param(
  [string]$Need = "我想买一台拍照好的安卓旗舰手机，预算5000左右",
  [string]$Query = "安卓旗舰手机 5000 拍照 评测"
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repoRoot
try {
  uv run voxlens-research search $Need --query $Query --platforms youtube,bilibili,xiaohongshu --limit 5
} finally {
  Pop-Location
}
