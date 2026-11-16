import hashlib
import subprocess
from pathlib import Path

# Project root: parent of agent_controller
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_current_commit() -> str:
    """Return the current Git commit hash."""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            "Could not retrieve the current Git commit."
        ) from error

    if result.returncode != 0:
        raise RuntimeError(
            "Git commit check failed:\n" + result.stderr.strip()
        )

    commit = result.stdout.strip()

    if not commit:
        raise RuntimeError("Git returned an empty commit hash.")

    return commit


def ensure_clean_working_tree() -> None:
    """Reject operations if tracked or untracked files have changed."""

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            "Could not verify Git working-tree status."
        ) from error

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
