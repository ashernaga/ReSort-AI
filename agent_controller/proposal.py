
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def validate_proposal(proposal: dict) -> bool:
    """Validate the structure and file paths of a proposed change."""

    if not isinstance(proposal, dict):
        raise ValueError("Proposal must be a JSON object.")

    required_fields = {"summary", "details", "files", "diff"}

    if set(proposal.keys()) != required_fields:
        raise ValueError(
            f"Proposal must contain exactly these fields: {required_fields}"
        )

    if not isinstance(proposal["summary"], str) or not proposal["summary"].strip():
        raise ValueError("Proposal summary is missing.")

    if not isinstance(proposal["details"], str) or not proposal["details"].strip():
        raise ValueError("Proposal details are missing.")

    if not isinstance(proposal["diff"], str) or not proposal["diff"].strip():
        raise ValueError("Proposal diff is missing.")

    files = proposal["files"]

    if not isinstance(files, list) or not files:
        raise ValueError("Proposal must specify at least one file.")

    for file_path in files:
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError("Invalid file path in proposal.")

        path = Path(file_path)

        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe file path: {file_path}")

        try:
            resolved = (PROJECT_ROOT / path).resolve()

            if not resolved.is_relative_to(PROJECT_ROOT):
                raise ValueError(f"Path escapes project directory: {file_path}")

        except (OSError, RuntimeError) as error:
            raise ValueError(f"Could not validate path: {file_path}") from error

    return True


def parse_proposal(raw_response: str) -> dict:
    """Parse and validate Claude's JSON proposal."""

    try:
        proposal = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise ValueError(
            "Claude did not return valid JSON. "
            "The proposal must be plain JSON without Markdown."
        ) from error

    validate_proposal(proposal)

    return proposal
