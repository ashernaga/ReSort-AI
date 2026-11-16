
from pathlib import Path

# Support both direct execution and package imports
if __package__:
    from .proposal import validate_proposal
    from .patch_applier import (
        get_current_commit,
        calculate_diff_hash,
    )
else:
    from proposal import validate_proposal
    from patch_applier import (
        get_current_commit,
        calculate_diff_hash,
    )


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def validate_proposal_files(files: list) -> bool:
    """Ensure proposed files are inside the project directory."""

    if not isinstance(files, list) or not files:
        print("REJECTED: No valid files specified.")
        return False

    for file_path in files:
        if not isinstance(file_path, str) or not file_path.strip():
            print("REJECTED: Invalid file path.")
            return False

        proposed_path = Path(file_path)

        if proposed_path.is_absolute():
            print(f"REJECTED: Absolute paths are not allowed: {file_path}")
            return False

        if ".." in proposed_path.parts:
            print(f"REJECTED: Parent-directory traversal detected: {file_path}")
            return False

        try:
            resolved_path = (PROJECT_ROOT / proposed_path).resolve()

            if not resolved_path.is_relative_to(PROJECT_ROOT):
                print(f"REJECTED: Path is outside the project: {file_path}")
                return False

        except (OSError, RuntimeError, ValueError):
            print(f"REJECTED: Could not validate path: {file_path}")
            return False

    return True


def request_approval(proposal: dict) -> dict | None:
    """
    Display a proposed change and request explicit approval.

    Returns an approval receipt containing the exact diff hash
    and Git baseline commit, or None if rejected.
    """

    if not isinstance(proposal, dict):
        print("REJECTED: Invalid proposal format.")
        return None

    try:
        validate_proposal(proposal)
    except (ValueError, RuntimeError) as error:
        print(f"REJECTED: Proposal validation failed: {error}")
        print("\nNo changes authorized.")
        return None

    files = proposal.get("files")

    if not validate_proposal_files(files):
        print("\nNo changes authorized.")
        return None

    print("\n" + "=" * 60)
    print("HUMAN APPROVAL REQUIRED")
    print("=" * 60)

    print("\nPROPOSED CHANGE:")
    print(proposal.get("summary", "No summary provided."))

    print("\nFILES AFFECTED:")

    for file_path in files:
        print(f"  - {file_path}")

    print("\nCHANGE DETAILS:")
    print(proposal.get("details", "No details provided."))

    print("\nEXACT PROPOSED DIFF:")
    print("=" * 60)
    print(proposal["diff"])
    print("=" * 60)

    # Capture the exact diff fingerprint before asking for approval.
    diff_hash = calculate_diff_hash(proposal["diff"])

    print("\n" + "-" * 60)
    print("Type APPROVE to accept this proposal.")
    print("Anything else will reject it.")

    decision = input("\nYour decision: ").strip()

    if decision != "APPROVE":
        print("\nProposal rejected. No changes authorized.")
        return None

    # Record the repository baseline at approval time.
    baseline_commit = get_current_commit()

    receipt = {
        "approved": True,
        "diff_hash": diff_hash,
        "baseline_commit": baseline_commit,
    }

    print("\nProposal approved by the user.")
    print("Approval receipt created.")

    return receipt