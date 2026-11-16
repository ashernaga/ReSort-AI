
import json
import subprocess
from pathlib import Path, PureWindowsPath

# Support both direct execution and package imports
if __package__:
    from .claude_agent import ask_claude
else:
    from claude_agent import ask_claude


PROJECT_ROOT = Path(__file__).resolve().parent.parent

def _check_git_patch(diff: str) -> None:
    """Check whether Git accepts a patch without applying it."""

    try:
        result = subprocess.run(
            ["git", "apply", "--check", "--"],
            cwd=str(PROJECT_ROOT),
            input=diff,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=30,
            check=False,
        )

    except FileNotFoundError as error:
        raise RuntimeError("Git executable was not found.") from error

    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            "Git patch validation timed out."
        ) from error

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()

        raise ValueError(
            "Git rejected the proposed patch:\n" + message
        )




def _validate_project_file(file_path: str) -> Path:
    """Validate that a path identifies an existing, regular project file."""

    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("Invalid file path.")

    if "\\" in file_path:
        raise ValueError(f"Use forward slashes in file paths: {file_path}")

    path = Path(file_path)
    windows_path = PureWindowsPath(file_path)

    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
        or ".." in path.parts
    ):
        raise ValueError(f"Unsafe file path: {file_path}")

    root = PROJECT_ROOT.resolve()
    candidate = root / path

    try:
        # Reject symbolic links in every path component.
        current = root

        for part in path.parts:
            current = current / part

            if current.is_symlink():
                raise ValueError(
                    f"Symbolic links are not allowed: {file_path}"
                )

        resolved = candidate.resolve(strict=True)

        if not resolved.is_relative_to(root):
            raise ValueError(
                f"Path escapes project directory: {file_path}"
            )

        if not resolved.is_file():
            raise ValueError(
                f"Path must identify an existing file: {file_path}"
            )

    except (OSError, RuntimeError) as error:
        raise ValueError(
            f"Could not validate file path: {file_path}"
        ) from error

    return resolved


def validate_proposal(proposal: dict) -> bool:
    """Validate proposal structure, file paths, and unified diff headers."""

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

    diff = proposal["diff"]

    if not isinstance(diff, str) or not diff.strip():
        raise ValueError("Proposal diff is missing.")

    files = proposal["files"]

    if not isinstance(files, list) or not files:
        raise ValueError("Proposal must specify at least one file.")

    validated_files = set()

    for file_path in files:
        _validate_project_file(file_path)

        if file_path in validated_files:
            raise ValueError(f"Duplicate file path: {file_path}")

        validated_files.add(file_path)

    # Extract and validate every unified diff file-header pair.
    diff_files = set()
    lines = diff.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]

        if line.startswith("--- "):
            if index + 1 >= len(lines):
                raise ValueError("Incomplete unified diff headers.")

            next_line = lines[index + 1]

            if not next_line.startswith("+++ "):
                raise ValueError("Malformed unified diff headers.")

            old_path = line[4:].split("\t", 1)[0]
            new_path = next_line[4:].split("\t", 1)[0]

            if not old_path.startswith("a/") or not new_path.startswith("b/"):
                raise ValueError(
                    "Only standard existing-file modifications are allowed."
                )

            old_file = old_path[2:]
            new_file = new_path[2:]

            if old_file != new_file:
                raise ValueError(
                    "File creation, deletion, and renaming are not allowed."
                )

            _validate_project_file(old_file)

            if old_file in diff_files:
                raise ValueError(
                    f"Duplicate file in diff: {old_file}"
                )

            diff_files.add(old_file)
            index += 2
            continue

        index += 1

    if not diff_files:
        raise ValueError("No valid unified diff file headers found.")

    if diff_files != validated_files:
        raise ValueError(
            "The files list does not match the files in the unified diff. "
            f"Listed: {sorted(validated_files)}; "
            f"Diff: {sorted(diff_files)}"
        )

    # Check the patch without applying any changes.
    _check_git_patch(diff)

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

def generate_proposal(task: str, investigation_plan: str = "") -> dict:
    """
    Ask Claude to inspect the project and return a proposed change.
    Claude must not modify any project files.
    """

    if not isinstance(task, str) or not task.strip():
        raise ValueError("A valid task description is required.")

    prompt = f"""
You are the proposal agent for the Trash ML Python project.

USER TASK:
{task}

INVESTIGATION PLAN:
{investigation_plan}

Your job is to inspect the relevant project files and propose
a specific code change.

STRICT RULES:
1. Do not create, edit, delete, or modify any files.
2. Do not apply your proposed changes.
3. Do not execute commands that modify the project.
4. Only inspect files relevant to the task.
5. Use paths relative to the project root.
6. Explain why the change is useful.
7. Provide a unified diff showing the exact proposed changes.
8. Include every affected file in the files list.
9. Do not include files that are not changed by the diff.

RETURN FORMAT:
Return ONLY valid JSON, without Markdown fences or explanations.

Use exactly this structure:
{{
    "summary": "Short description of the proposed change",
    "details": "Explanation and reasoning",
    "files": ["relative/path/to/file.py"],
    "diff": "Unified diff as a JSON string"
}}

The diff must use standard unified diff headers.
Do not claim that changes have been applied.
"""

    print("\nClaude is preparing a proposed change...")

    raw_response = ask_claude(prompt)

    proposal = parse_proposal(raw_response)

    print("Claude proposal received and validated.")

    return proposal