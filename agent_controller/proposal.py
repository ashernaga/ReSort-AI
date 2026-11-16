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

    # Confirm that Git already tracks this file.
    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                file_path,
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ValueError(
            f"Git tracking check timed out: {file_path}"
        ) from error

    if result.returncode != 0:
        raise ValueError(
            f"File is not tracked by Git: {file_path}"
        )

    return resolved


def _validate_unified_diff(diff: str) -> set:
    """Accept only standard unified diffs modifying existing project files."""

    import re

    lines = diff.splitlines()
    diff_files = set()
    index = 0

    hunk_pattern = re.compile(
        r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
    )

    while index < len(lines):
        # Every file section must begin with standard unified headers.
        if not lines[index].startswith("--- a/"):
            raise ValueError(
                "Unsupported diff metadata or malformed file header."
            )

        old_path = lines[index][4:].split("\t", 1)[0]

        if index + 1 >= len(lines):
            raise ValueError("Incomplete unified diff headers.")

        if not lines[index + 1].startswith("+++ b/"):
            raise ValueError("Malformed unified diff headers.")

        new_path = lines[index + 1][4:].split("\t", 1)[0]

        if old_path[2:] != new_path[2:]:
            raise ValueError(
                "File creation, deletion, and renaming are not allowed."
            )

        file_path = old_path[2:]
        _validate_project_file(file_path)

        if file_path in diff_files:
            raise ValueError(f"Duplicate file in diff: {file_path}")

        diff_files.add(file_path)
        index += 2

        hunk_count = 0

        while index < len(lines) and not lines[index].startswith("--- a/"):
            match = hunk_pattern.fullmatch(lines[index])

            if not match:
                raise ValueError(
                    "Unsupported diff metadata or malformed hunk header."
                )

            old_expected = (
                int(match.group(2)) if match.group(2) is not None else 1
            )
            new_expected = (
                int(match.group(4)) if match.group(4) is not None else 1
            )
            old_seen = 0
            new_seen = 0
            index += 1

            while (
                old_seen < old_expected
                or new_seen < new_expected
            ):
                if index >= len(lines):
                    raise ValueError("Incomplete diff hunk.")

                line = lines[index]

                if line.startswith(" "):
                    old_seen += 1
                    new_seen += 1
                elif line.startswith("+"):
                    new_seen += 1
                elif line.startswith("-"):
                    old_seen += 1
                elif line == "\\ No newline at end of file":
                    pass
                else:
                    raise ValueError("Invalid unified diff hunk line.")

                if (
                    old_seen > old_expected
                    or new_seen > new_expected
                ):
                    raise ValueError("Diff hunk line counts do not match.")

                index += 1

                if (
                    index < len(lines)
                    and lines[index] == "\\ No newline at end of file"
                ):
                    index += 1

            hunk_count += 1

        if hunk_count == 0:
            raise ValueError("Every modified file must contain a diff hunk.")

    if not diff_files:
        raise ValueError("No valid unified diff file headers found.")

    return diff_files



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

    # Validate the complete unified diff structure.
    diff_files = _validate_unified_diff(diff)

    # Ensure the declared files match the actual diff.
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