
from pathlib import Path

# Project root: parent directory of agent_controller
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def validate_proposal_files(files: list) -> bool:
    """
    Ensure every proposed file is inside the project directory.
    Reject absolute paths, traversal, and paths outside the project.
    """

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


def request_approval(proposal: dict) -> bool:
    """
    Display a proposed change and request explicit human approval.
    Returns True only when the user enters exactly APPROVE.
    """

    if not isinstance(proposal, dict):
        print("REJECTED: Invalid proposal format.")
        return False

    files = proposal.get("files")

    if not validate_proposal_files(files):
        print("\nNo changes authorized.")
        return False

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

    print("\n" + "-" * 60)
    print("Type APPROVE to accept this proposal.")
    print("Anything else will reject it.")

    decision = input("\nYour decision: ").strip()

    if decision == "APPROVE":
        print("\nProposal approved by the user.")
        return True

    print("\nProposal rejected. No changes authorized.")
    return False
