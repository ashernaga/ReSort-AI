
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path

if __package__:
    from .receipts import consume_receipt, verify_signature
else:
    from receipts import consume_receipt, verify_signature

# Project root: parent of agent_controller
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_git(
    args: list,
    cwd: Path,
    input_text: str = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Run Git safely without invoking a shell."""

    # Send input as raw UTF-8 bytes. A text-mode pipe on Windows would
    # rewrite every LF as CRLF, so Git would receive a different patch
    # from the one that was approved and fingerprinted.
    input_bytes = (
        input_text.encode("utf-8") if input_text is not None else None
    )

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            "Git command failed or timed out."
        ) from error

    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )


def _is_registered_worktree(worktree_path: Path) -> bool:
    """Check whether Git has registered the specified worktree."""

    result = _run_git(
        ["worktree", "list", "--porcelain"],
        PROJECT_ROOT,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Could not inspect Git worktree registrations:\n"
            + result.stderr.strip()
        )

    expected_path = os.path.normcase(
        os.path.abspath(str(worktree_path))
    )

    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            registered_path = line[len("worktree "):]

            actual_path = os.path.normcase(
                os.path.abspath(registered_path)
            )

            if actual_path == expected_path:
                return True

    return False


def _hash_file(cwd: Path, file_path: str) -> str:
    """
    Return Git's content hash of a working-tree file.

    Git applies its normal line-ending conversion, so the same content
    gives the same hash in the temporary worktree and the real project.
    """

    result = _run_git(["hash-object", "--", file_path], cwd, timeout=10)

    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(
            f"Could not fingerprint file contents: {file_path}"
        )

    return result.stdout.strip()


def get_current_commit() -> str:
    """Return the current Git commit hash."""

    result = _run_git(
        ["rev-parse", "HEAD"],
        PROJECT_ROOT,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Git commit check failed:\n" + result.stderr.strip()
        )

    commit = result.stdout.strip()

    if not commit:
        raise RuntimeError("Git returned an empty commit hash.")

    return commit


def ensure_clean_working_tree() -> None:
    """
    Reject operations if tracked or untracked files have changed.

    Files ignored by Git are deliberately not checked. The project
    always contains ignored files (venv, .env, models, datasets), and
    proposals can only modify tracked files.
    """

    result = _run_git(
        ["status", "--porcelain", "--untracked-files=all"],
        PROJECT_ROOT,
        timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Git status check failed:\n" + result.stderr.strip()
        )

    if result.stdout.strip():
        raise ValueError(
            "Working tree is not clean. No patch can be applied:\n"
            + result.stdout.strip()
        )


def calculate_diff_hash(diff: str) -> str:
    """Calculate a SHA-256 fingerprint of the exact proposed diff."""

    if not isinstance(diff, str) or not diff:
        raise ValueError("Cannot fingerprint an empty or invalid diff.")

    return hashlib.sha256(diff.encode("utf-8")).hexdigest()


def verify_approval_receipt(proposal: dict, receipt: dict) -> bool:
    """
    Verify that an approval receipt matches the exact proposal
    and the current Git baseline.

    This function does not apply any changes.
    """

    if not isinstance(proposal, dict):
        raise ValueError("Invalid proposal.")

    if not isinstance(receipt, dict):
        raise ValueError("Invalid approval receipt.")

    if not verify_signature(receipt):
        raise ValueError(
            "Approval receipt is not signed by this approval session. "
            "It may be forged, edited, or from an earlier run."
        )

    if receipt.get("approved") is not True:
        raise ValueError("Proposal has not been approved.")

    proposed_diff = proposal.get("diff")

    if not isinstance(proposed_diff, str) or not proposed_diff:
        raise ValueError("Proposal contains no valid diff.")

    expected_hash = calculate_diff_hash(proposed_diff)

    if receipt.get("diff_hash") != expected_hash:
        raise ValueError(
            "Approval fingerprint does not match the proposed diff."
        )

    baseline_commit = receipt.get("baseline_commit")

    if not isinstance(baseline_commit, str) or not baseline_commit:
        raise ValueError("Approval receipt has no valid baseline commit.")

    current_commit = get_current_commit()

    if current_commit != baseline_commit:
        raise ValueError(
            "Git baseline has changed since approval. "
            "A new approval is required."
        )

    ensure_clean_working_tree()

    return True


def validate_patch_application(proposal: dict, receipt: dict) -> bool:
    """
    Perform safety checks before patch application.

    This is a dry-run validation only.
    No project files are modified.
    """

    if __package__:
        from .proposal import validate_proposal
    else:
        from proposal import validate_proposal

    verify_approval_receipt(proposal, receipt)

    baseline_commit = receipt["baseline_commit"]

    validate_proposal(proposal)

    if get_current_commit() != baseline_commit:
        raise RuntimeError(
            "Git baseline changed during patch validation."
        )

    ensure_clean_working_tree()

    if calculate_diff_hash(proposal["diff"]) != receipt["diff_hash"]:
        raise ValueError(
            "Proposal diff changed during patch validation."
        )

    return True


def verify_patch_in_temporary_worktree(
    proposal: dict,
    receipt: dict,
) -> dict:
    """
    Test an approved patch inside a temporary detached Git worktree.

    The real project files are never modified by the patch.
    No commit, merge, or copy-back operation is performed.
    """

    if __package__:
        from .proposal import validate_proposal
    else:
        from proposal import validate_proposal

    # Verify approval, baseline, and original working-tree cleanliness.
    verify_approval_receipt(proposal, receipt)

    baseline_commit = receipt["baseline_commit"]
    approved_diff = proposal["diff"]
    approved_hash = receipt["diff_hash"]

    # Revalidate proposal paths and diff structure.
    validate_proposal(proposal)

    # Confirm that the original repository is still unchanged.
    if get_current_commit() != baseline_commit:
        raise RuntimeError(
            "Git baseline changed during proposal validation."
        )

    ensure_clean_working_tree()

    if calculate_diff_hash(approved_diff) != approved_hash:
        raise ValueError(
            "Proposal diff changed during validation."
        )

    expected_files = set(proposal["files"])

    with tempfile.TemporaryDirectory(
        prefix="trash_ml_patch_test_"
    ) as temporary_directory:

        worktree_path = Path(temporary_directory) / "worktree"

        try:
            # Create an isolated worktree at the approved commit.
            add_result = _run_git(
                [
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree_path),
                    baseline_commit,
                ],
                PROJECT_ROOT,
                timeout=60,
            )

            # Check Git's registry even if the add command failed.
            worktree_registered = _is_registered_worktree(
                worktree_path
            )

            if add_result.returncode != 0:
                raise RuntimeError(
                    "Could not create temporary Git worktree:\n"
                    + add_result.stderr.strip()
                )

            if not worktree_registered:
                raise RuntimeError(
                    "Git did not register the temporary worktree."
                )

            # Confirm the temporary worktree starts at the approved commit.
            head_result = _run_git(
                ["rev-parse", "HEAD"],
                worktree_path,
                timeout=10,
            )

            if head_result.returncode != 0:
                raise RuntimeError(
                    "Could not verify temporary worktree commit."
                )

            if head_result.stdout.strip() != baseline_commit:
                raise RuntimeError(
                    "Temporary worktree does not match "
                    "the approved baseline."
                )

            # Check the exact approved patch before applying it.
            check_result = _run_git(
                ["apply", "--check", "--"],
                worktree_path,
                input_text=approved_diff,
                timeout=30,
            )

            if check_result.returncode != 0:
                raise ValueError(
                    "Approved patch failed Git apply check:\n"
                    + check_result.stderr.strip()
                )

            # Apply the exact same diff without regenerating it.
            apply_result = _run_git(
                ["apply", "--"],
                worktree_path,
                input_text=approved_diff,
                timeout=30,
            )

            if apply_result.returncode != 0:
                raise RuntimeError(
                    "Patch application failed in temporary worktree:\n"
                    + apply_result.stderr.strip()
                )

            # Confirm that the patch did not create untracked files.
            untracked_result = _run_git(
                [
                    "ls-files",
                    "--others",
                    "-z",
                ],
                worktree_path,
                timeout=10,
            )

            if untracked_result.returncode != 0:
                raise RuntimeError(
                    "Could not verify temporary worktree files."
                )

            if untracked_result.stdout:
                raise ValueError(
                    "Patch created unexpected untracked files."
                )
                        # Confirm that the patch did not stage any changes.
            staged_result = _run_git(
                ["diff", "--cached", "--quiet"],
                worktree_path,
                timeout=10,
            )

            if staged_result.returncode == 1:
                raise ValueError(
                    "Patch produced unexpected staged changes."
                )

            if staged_result.returncode != 0:
                raise RuntimeError(
                    "Could not verify staged changes."
                )

            # Inspect actual changed paths and change types.
            changes_result = _run_git(
                [
                    "diff",
                    "--name-status",
                    "--no-renames",
                    "-z",
                ],
                worktree_path,
                timeout=10,
            )

            if changes_result.returncode != 0:
                raise RuntimeError(
                    "Could not inspect temporary worktree changes."
                )

            records = [
                record
                for record in changes_result.stdout.split("\0")
                if record
            ]

            if len(records) % 2 != 0:
                raise RuntimeError(
                    "Unexpected Git change-list format."
                )

            actual_files = set()

            for index in range(0, len(records), 2):
                change_type = records[index]
                file_path = records[index + 1]

                # Only modifications to existing files are permitted.
                if change_type != "M":
                    raise ValueError(
                        "Unexpected patch change type: "
                        + change_type
                    )

                actual_files.add(file_path)

            if actual_files != expected_files:
                raise ValueError(
                    "Patch changed files outside the approved file list. "
                    f"Expected: {sorted(expected_files)}; "
                    f"actual: {sorted(actual_files)}"
                )

            # Verify the temporary worktree HEAD was not changed.
            final_head = _run_git(
                ["rev-parse", "HEAD"],
                worktree_path,
                timeout=10,
            )

            if (
                final_head.returncode != 0
                or final_head.stdout.strip() != baseline_commit
            ):
                raise RuntimeError(
                    "Temporary worktree commit changed unexpectedly."
                )

            # Verify that the original repository remains unchanged.
            if get_current_commit() != baseline_commit:
                raise RuntimeError(
                    "Original repository commit changed "
                    "during verification."
                )

            ensure_clean_working_tree()

            if calculate_diff_hash(approved_diff) != approved_hash:
                raise ValueError(
                    "Approved diff fingerprint changed "
                    "during verification."
                )

            # Record the resulting content of every changed file, so a
            # later real application can be compared with this result.
            file_hashes = {
                file_path: _hash_file(worktree_path, file_path)
                for file_path in sorted(actual_files)
            }

            return {
                "verified": True,
                "baseline_commit": baseline_commit,
                "changed_files": sorted(actual_files),
                "diff_hash": approved_hash,
                "file_hashes": file_hashes,
            }

        finally:
            # Always inspect Git's registry, including after partial failure.
            if _is_registered_worktree(worktree_path):
                remove_result = _run_git(
                    [
                        "worktree",
                        "remove",
                        "--force",
                        str(worktree_path),
                    ],
                    PROJECT_ROOT,
                    timeout=60,
                )

                if remove_result.returncode != 0:
                    raise RuntimeError(
                        "Could not clean up temporary Git worktree:\n"
                        + remove_result.stderr.strip()
                    )


def _parse_name_status(output: str) -> dict:
    """Parse `git diff --name-status --no-renames -z` into {path: type}."""

    records = [record for record in output.split("\0") if record]

    if len(records) % 2 != 0:
        raise RuntimeError("Unexpected Git change-list format.")

    return {
        records[index + 1]: records[index]
        for index in range(0, len(records), 2)
    }


def _verify_applied_result(
    baseline_commit: str,
    expected_files: set,
    expected_hashes: dict,
) -> None:
    """
    Check the real project after a patch was applied.

    Raises if anything differs from what was approved and verified.
    """

    if get_current_commit() != baseline_commit:
        raise RuntimeError("Git commit changed during application.")

    staged = _run_git(["diff", "--cached", "--quiet"], PROJECT_ROOT)

    if staged.returncode == 1:
        raise RuntimeError("Unexpected staged changes after application.")

    if staged.returncode != 0:
        raise RuntimeError("Could not check staged changes.")

    untracked = _run_git(
        ["ls-files", "--others", "--exclude-standard", "-z"],
        PROJECT_ROOT,
    )

    if untracked.returncode != 0:
        raise RuntimeError("Could not check for new files.")

    if untracked.stdout:
        raise RuntimeError("Application created unexpected new files.")

    changes = _run_git(
        ["diff", "--name-status", "--no-renames", "-z"],
        PROJECT_ROOT,
    )

    if changes.returncode != 0:
        raise RuntimeError("Could not list changed files.")

    changed = _parse_name_status(changes.stdout)

    if any(kind != "M" for kind in changed.values()):
        raise RuntimeError(
            "Application made a change other than modifying a file."
        )

    if set(changed) != set(expected_files):
        raise RuntimeError(
            "Changed files differ from the approved list. "
            f"Expected: {sorted(expected_files)}; "
            f"actual: {sorted(changed)}"
        )

    for file_path in sorted(expected_files):
        if _hash_file(PROJECT_ROOT, file_path) != expected_hashes[file_path]:
            raise RuntimeError(
                "File contents differ from the verified result: "
                + file_path
            )


def _undo_command(files: list) -> str:
    quoted = " ".join(f'"{name}"' for name in files)

    return f"git restore -- {quoted}"


def _rollback_patch(diff: str, files: list) -> str:
    """
    Undo an applied patch by reverse-applying the exact approved diff.

    Only the patch's own changes are reversed, so unrelated edits are
    never discarded. Returns a message describing the outcome.
    """

    check = _run_git(
        ["apply", "-R", "--check", "--"], PROJECT_ROOT, input_text=diff
    )

    if check.returncode == 0:
        undone = _run_git(
            ["apply", "-R", "--"], PROJECT_ROOT, input_text=diff
        )

        if undone.returncode == 0:
            try:
                ensure_clean_working_tree()
                return "The patch was rolled back. Your files are unchanged."
            except (ValueError, RuntimeError):
                return (
                    "The patch was rolled back. Other changes in your "
                    "working tree were not made by this patch and were "
                    "left untouched; inspect them with 'git status'."
                )

    return (
        "AUTOMATIC ROLLBACK FAILED. Your files were left as they are. "
        "Inspect them with 'git diff'. If you want to discard the "
        "patch's changes, run: " + _undo_command(files)
    )


def apply_approved_patch(proposal: dict, receipt: dict) -> dict:
    """
    Apply an approved proposal to the real project.

    Order of operations:
    1. Verify the exact patch in a temporary worktree.
    2. Re-check the receipt, baseline, working tree, paths, and diff.
    3. Spend the single-use receipt.
    4. Apply the exact approved diff.
    5. Verify the result against what the temporary worktree produced.
    6. Reverse the patch if the result is not exactly as verified.

    The change is left uncommitted. Nothing is staged.
    """

    if __package__:
        from .proposal import validate_proposal
    else:
        from proposal import validate_proposal

    # Sandbox verification also checks the receipt and the working tree.
    verification = verify_patch_in_temporary_worktree(proposal, receipt)

    baseline_commit = receipt["baseline_commit"]
    approved_diff = proposal["diff"]
    files = sorted(proposal["files"])

    # Final re-validation immediately before touching the project.
    verify_approval_receipt(proposal, receipt)
    validate_proposal(proposal)

    if calculate_diff_hash(approved_diff) != receipt["diff_hash"]:
        raise ValueError("Proposal diff changed before application.")

    if (
        verification["baseline_commit"] != baseline_commit
        or verification["diff_hash"] != receipt["diff_hash"]
        or verification["changed_files"] != files
    ):
        raise RuntimeError(
            "Verification result does not match the approved proposal."
        )

    ensure_clean_working_tree()

    # From here the approval is spent, whatever happens next.
    consume_receipt(receipt)

    check = _run_git(
        ["apply", "--check", "--"], PROJECT_ROOT, input_text=approved_diff
    )

    if check.returncode != 0:
        raise ValueError(
            "Approved patch no longer applies. Nothing was changed:\n"
            + check.stderr.strip()
        )

    applied = _run_git(
        ["apply", "--"], PROJECT_ROOT, input_text=approved_diff
    )

    if applied.returncode != 0:
        # git apply is all-or-nothing, but confirm nothing changed.
        try:
            ensure_clean_working_tree()
            state = "Nothing was changed."
        except (ValueError, RuntimeError):
            state = (
                "The working tree is not clean; inspect it with "
                "'git diff'."
            )

        raise RuntimeError(
            "Patch application failed. "
            + state
            + "\n"
            + applied.stderr.strip()
        )

    try:
        _verify_applied_result(
            baseline_commit, set(files), verification["file_hashes"]
        )
    except (ValueError, RuntimeError) as error:
        outcome = _rollback_patch(approved_diff, files)

        raise RuntimeError(
            f"Applied patch failed verification: {error}\n{outcome}"
        ) from error

    return {
        "applied": True,
        "baseline_commit": baseline_commit,
        "changed_files": files,
        "diff_hash": receipt["diff_hash"],
        "file_hashes": verification["file_hashes"],
        "undo_command": _undo_command(files),
    }
