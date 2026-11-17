# Trash ML — Claude Code Project Instructions

## 1. Project overview

This is a Python-based machine learning project called Trash ML.

The original ML system uses TensorFlow and MobileNetV2 to classify waste into four categories:

- glass
- plastic
- metal
- general_waste

The project is also developing a GPT–Claude multi-agent coding system.

## 2. Development environment

- OS: Windows
- IDE: Visual Studio Code
- Terminal: PowerShell
- Python: 3.11.9
- Existing virtual environment: `venv`
- TensorFlow: 2.21.0
- OpenAI Python package installed
- Claude Code CLI installed and authenticated

Project root:
`C:\Users\ASUS\BU\project\hult prize\Trash ML`

Do not create another virtual environment. Use the existing `venv`.

## 3. Multi-agent architecture

The intended workflow is:

1. User describes a coding task.
2. GPT analyzes the task and creates an investigation plan.
3. Claude inspects the project and proposes a code change.
4. The user reviews the proposal and exact diff.
5. The user explicitly approves or rejects it.
6. A controlled mechanism validates and applies approved changes.
7. GPT reviews the resulting diff and test results.
8. The user receives the final report.

GPT is the planner and reviewer.
Claude is the developer and investigator.
The user retains final approval authority.

## 4. Critical safety requirements

These requirements must not be weakened.

- Never use `--dangerously-skip-permissions`.
- Do not give Claude unrestricted write permissions.
- Preserve explicit human approval.
- Never apply an unapproved patch.
- Apply the exact diff that was approved.
- Verify the approval fingerprint before application.
- Verify the Git baseline before application.
- Reject dirty working trees.
- Validate all proposed paths.
- Reject paths outside the project.
- Reject Git metadata modifications.
- Reject file creation, deletion, and renaming unless explicitly reviewed and separately authorized.
- Use Git checkpoints.
- Do not expose API keys or `.env` contents.
- Do not overwrite existing work without inspecting it first.
- Never silently discard user changes.
- Run tests before declaring a task complete.

Normal Claude Code permission prompts must remain enabled.

## 5. Current Git state

Main development branch:

`feature/human-approval-workflow`

All controller work lives on this branch and is local only: nothing has
been pushed to the remote. Use `git log` and `git status` for the exact
current commit and working-tree state; do not rely on a hash written here.

Other worktrees that exist:

- `.claude/worktrees/esp32-cam-capture-issue-b59944` (do not modify or
  remove it without explicit authorization)
- `Trash ML agent1` and `Trash ML agent2` (branches `agent1/work` and
  `agent2/work`, created by `scripts/setup_agents.ps1`). They were created
  from an older commit and may run outdated controller code until their
  branches are updated.
- Session worktrees under `.claude/worktrees/`

Never reset, restore, overwrite, or discard uncommitted work without
inspecting it first.

## 6. Multi-agent controller files

The `agent_controller` directory contains:

- `approval.py`
- `checks.py`
- `claude_agent.py`
- `config.py`
- `main.py`
- `openai_agent.py`
- `patch_applier.py`
- `proposal.py`
- `receipts.py`
- `reviewer.py`

Tests are in `tests/` and run with:

`venv\Scripts\python.exe -B -m unittest discover -s tests -t . -v`

Proposals can never modify `agent_controller/`, `scripts/`, `tests/`,
`CLAUDE.md`, or tool configuration (`.git*`, `.vscode`, `.claude`,
`.agents`, `.github`, `.env*`). Change those files by hand.

Important existing functionality:

### openai_agent.py
Communicates with OpenAI through the Responses API.

### claude_agent.py
Runs Claude Code CLI in plan mode.

Keep Claude in plan mode for the existing proposal workflow.

An optional `CLAUDE_MODEL` setting (environment variable or `.env`)
selects the model passed to the CLI with `--model`. If it is unset the
CLI default is used; that default may require usage credits, in which case
the run fails with a message saying so.

### proposal.py
Parses and validates Claude proposals.

It includes:
- JSON validation
- Project path validation, including protected paths
- Git tracking checks
- Symlink checks
- Windows path restrictions
- Unified diff validation
- Git patch validation
- Rejection of control characters and invisible or bidirectional Unicode
  in the summary, details, and diff, so displayed text equals applied text
- Normalization of common diff formatting (`diff --git` and `index` lines,
  empty context lines, missing final newline) at parse time only. The
  normalized diff is the one that is displayed, fingerprinted, and applied.
  Validation itself stays strict.

Claude gets three attempts per proposal; each rejection reason is fed back.

### approval.py
Displays proposals and exact diffs.

Only the exact input `APPROVE` (surrounding spaces are ignored) authorizes
a proposal. The screen states that approving will modify files.

The approval receipt contains:
- approved
- diff_hash
- baseline_commit
- signature

### receipts.py
Signs receipts with a random per-run key held only in memory, and spends
each receipt once. This stops forged, edited, stale, and reused receipts.
It is not a defence against malicious code in the same Python process.

### patch_applier.py
Contains Git safety checks, receipt verification, dry-run validation,
temporary worktree verification, and controlled application.

`apply_approved_patch` runs this order: sandbox verification, full
re-validation, spend the receipt, apply the exact approved diff, verify
the result (HEAD unchanged, nothing staged, no new files, only approved
files modified as plain modifications, content hashes equal to the sandbox
result), and reverse-apply the patch if verification fails. Rollback only
reverses the patch itself, so unrelated edits are never discarded. The
change is left uncommitted and unstaged.

Ignored files do not block a run; the project always contains some
(`venv`, `.env`, `models`, datasets).

### checks.py
Parses changed Python files and runs the project's unittest suite. It only
reports. The only suite is the controller's own, so for ML changes it does
not exercise the change itself.

### reviewer.py
Sends the task, proposal, real applied diff, and check results to GPT for a
verdict. It reports only and cannot modify files. Its output is stripped of
control characters before printing.

### main.py
Runs six stages: GPT plan, Claude proposal, human approval, verify and
apply, checks, GPT review. It refuses to start if the working tree is not
clean, before any API call. The applied change is left uncommitted; the
user inspects `git diff`, then commits or undoes it.

## 7. Remaining development objectives

Work through these objectives sequentially.

### Status

- Phases 1-4 are implemented and covered by the unit tests in `tests/`
  (temporary Git repositories, LF and CRLF working files, GPT and Claude
  replaced by stand-ins).
- Phase 5 is partly done. A live run has confirmed GPT planning, Claude
  proposal generation, validation, and the approval prompt (rejected, so
  nothing was applied). A live approved application, the live checks, and
  the live GPT review have NOT been run yet. The first one should be a
  small harmless change that the user approves personally.
- Known limitations: receipts do not defend against hostile code in the
  same process; look-alike Unicode letters are not detected; there is a
  tiny window between the last check and the apply (the post-apply hash
  comparison catches it and rolls back); the test suite does not exercise
  ML changes.

### Phase 1 — Finish safety review

- Inspect current changes in `patch_applier.py`.
- Inspect `proposal.py`.
- Review path validation and diff validation.
- Review temporary worktree cleanup.
- Check for unexpected staged, unstaged, ignored, and untracked files.
- Identify security limitations.
- Avoid unnecessary rewrites.

### Phase 2 — Complete testing

Test:
- Valid proposals
- Invalid approval receipts
- Modified diff fingerprints
- Incorrect Git baselines
- Dirty working trees
- Malicious paths
- Mismatched declared file lists
- Invalid Git patches
- Unexpected staged changes
- Unexpected untracked and ignored files
- Temporary worktree cleanup after errors

Use separate temporary Git repositories where possible.

Never experiment with destructive changes in the real project.

### Phase 3 — Controlled patch application

Only after the safety review and tests pass:

- Design a controlled application mechanism.
- Require explicit approval.
- Verify the exact approved diff.
- Verify the Git baseline.
- Revalidate paths immediately before applying.
- Apply only the approved diff.
- Verify resulting changed files.
- Preserve recovery options.

Do not assume temporary worktree verification is equivalent to safe real-project application.

### Phase 4 — GPT final reviewer

Implement a GPT review stage that examines:
- Original task
- Claude proposal
- Applied diff
- Test results
- Potential regressions
- Whether the task was completed

GPT should report problems rather than silently modifying files.

### Phase 5 — End-to-end testing

Test the complete workflow:

GPT planner → Claude developer → Human approval → Controlled patch application → Tests → GPT reviewer.

## 8. Working style

The project owner prefers:

- Step-by-step instructions
- PowerShell commands
- Complete code replacements when necessary
- One stage at a time
- Explanations before important changes
- Test results before moving to the next stage

Do not make multiple unrelated changes at once.

Before modifying files:

1. Inspect Git status.
2. Inspect the relevant source code.
3. Explain the proposed change.
4. Identify risks.
5. Wait for user authorization when the change is significant.

After modifying files:

1. Run Python syntax checks.
2. Run relevant tests.
3. Run `git diff --check`.
4. Inspect the resulting diff.
5. Report exactly which files changed.

Never claim a test passed without actually running it.

## 9. First task for Claude Code

Start by inspecting the repository without modifying any files.

Specifically:

1. Run `git status --short`.
2. Run `git rev-parse --short HEAD`.
3. Inspect the current `patch_applier.py`.
4. Inspect `proposal.py`.
5. Inspect `approval.py`.
6. Inspect `main.py`.
7. Review the existing tests and test history if available.
8. Compare the current implementation with these instructions.

Then provide:

- Current development status
- Confirmed completed functionality
- Outstanding issues
- Safety risks
- Recommended next steps

Do not edit, reset, commit, or apply anything during this initial inspection.

Wait for the user's approval before starting modifications.