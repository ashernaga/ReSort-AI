# Runs the GPT + Claude approval workflow inside one agent's own worktree.
param([ValidateSet(1, 2)][int]$Agent = 1)

$ErrorActionPreference = "Stop"
$root   = (Resolve-Path "$PSScriptRoot\..").Path
$path   = Join-Path (Split-Path $root -Parent) "Trash ML agent$Agent"
$python = Join-Path $root "venv\Scripts\python.exe"

if (-not (Test-Path $path))   { throw "Worktree missing. Run .\scripts\setup_agents.ps1 first." }
if (-not (Test-Path $python)) { throw "venv not found at $python" }

Set-Location $path
Write-Host "Agent $Agent workspace: $path"
Write-Host "Branch: $(git rev-parse --abbrev-ref HEAD)"
& $python -m agent_controller.main
