# Self-contained push script: runs checks and pushes main branch to GitHub.
$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = 1

Write-Host "== 1. Running linter and format check ==" -ForegroundColor Cyan
uv run ruff check .
uv run ruff format --check .

Write-Host "== 2. Running pytest suite ==" -ForegroundColor Cyan
uv run pytest -q

Write-Host "== 3. Checking Git status ==" -ForegroundColor Cyan
$status = git status --porcelain
if ($status) {
    Write-Host "Working tree has uncommitted changes:" -ForegroundColor Yellow
    git status --short
    exit 1
}

Write-Host "== 4. Pushing to GitHub (origin main) ==" -ForegroundColor Cyan
git push origin main
Write-Host "Push successful! Repository is live at https://github.com/SerjCallier/hacom-ai-telco-engine" -ForegroundColor Green
