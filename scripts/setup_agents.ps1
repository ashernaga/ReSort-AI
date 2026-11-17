# Creates two isolated agent workspaces (git worktrees) next to this project.
# Safe to re-run: existing worktrees are left alone.
param([string]$BaseBranch = "")

$ErrorActionPreference = "Stop"
$root   = (Resolve-Path "$PSScriptRoot\..").Path
$parent = Split-Path $root -Parent
Set-Location $root

if (-not $BaseBranch) { $BaseBranch = (git rev-parse --abbrev-ref HEAD).Trim() }
Write-Host "Project : $root"
Write-Host "Base    : $BaseBranch"

if (git status --porcelain --untracked-files=all) {
    Write-Warning "Main folder has uncommitted changes. Worktrees start from the last commit, so commit first if you want them included."
}

foreach ($n in 1, 2) {
    $path   = Join-Path $parent "Trash ML agent$n"
    $branch = "agent$n/work"
    Write-Host "`n--- Agent $n -> $path ($branch)"

    if (-not (Test-Path $path)) {
        git show-ref --verify --quiet "refs/heads/$branch"
        if ($LASTEXITCODE -eq 0) { git worktree add $path $branch }
        else                     { git worktree add -b $branch $path $BaseBranch }
        if ($LASTEXITCODE -ne 0) { throw "Could not create worktree for agent $n" }
    } else {
        Write-Host "Worktree already exists, keeping it."
    }

    # Untracked-but-needed files (all gitignored, so they never dirty the tree)
    if ((Test-Path "$root\.env") -and -not (Test-Path "$path\.env")) {
        Copy-Item "$root\.env" "$path\.env"
    }
    if ((Test-Path "$root\models") -and -not (Test-Path "$path\models")) {
        Copy-Item "$root\models" "$path\models" -Recurse   # own copy: agents must not overwrite each other's model
    }
    if ((Test-Path "$root\dataset_split") -and -not (Test-Path "$path\dataset_split")) {
        New-Item -ItemType Junction -Path "$path\dataset_split" -Target "$root\dataset_split" | Out-Null   # shared, read-only use
    }

    Push-Location $path
    $dirty = git status --porcelain --untracked-files=all
    Pop-Location
    if ($dirty) { Write-Warning "Agent $n tree is NOT clean:`n$dirty" } else { Write-Host "Agent $n tree is clean." }
}

Write-Host "`nWorktrees:"
git worktree list
Write-Host "`nRun an agent with:  .\scripts\run_agent.ps1 -Agent 1   (or 2)"
