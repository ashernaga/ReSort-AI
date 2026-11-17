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

Current branch:

`feature/human-approval-workflow`

Last confirmed commit:

`b97f3a4`

Commit description:

`Strengthen proposal path validation`

The following file has uncommitted changes:

`agent_controller/patch_applier.py`

A backup was created at:

`%TEMP%\patch_applier_before_review.py`

The backup SHA-256 and the working file SHA-256 matched when created.

Do not reset, restore, overwrite, or discard this file.

The separate Claude worktree also exists:

`.claude/worktrees/esp32-cam-capture-issue-b59944`

Do not modify or remove it without explicit authorization.

## 6. Multi-agent controller files

The `agent_controller` directory contains:

- `approval.py`
- `claude_agent.py`
- `config.py`
- `main.py`
- `openai_agent.py`
- `proposal.py`
- `patch_applier.py`

Important existing functionality:

### openai_agent.py
Communicates with OpenAI through the Responses API.

### claude_agent.py
Runs Claude Code CLI in plan mode.

Keep Claude in plan mode for the existing proposal workflow.

### proposal.py
Parses and validates Claude proposals.

It includes:
- JSON validation
- Project path validation
- Git tracking checks
- Symlink checks
- Windows path restrictions
- Unified diff validation
- Git patch validation

### approval.py
Displays proposals and exact diffs.

Only the exact input `APPROVE` authorizes a proposal.

The approval receipt contains:
- approved
- diff_hash
- baseline_commit

### patch_applier.py
Contains Git safety checks, approval receipt verification, dry-run validation, and temporary worktree verification.

It currently includes an uncommitted implementation.

It has passed isolated tests for:
- Successful temporary patch verification
- Invalid approval receipt rejection
- Incorrect baseline rejection
- Invalid patch rejection
- Temporary worktree cleanup
- Original repository preservation

Additional staged-change and untracked-file checks have recently been added but need retesting.

The temporary worktree verifier does not yet apply patches to the real project.

### main.py
Currently connects GPT planning, Claude proposal generation, human approval, and dry-run validation.

It does not yet perform actual patch application.

## 7. Remaining development objectives

Work through these objectives sequentially.

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