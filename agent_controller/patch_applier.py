
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
