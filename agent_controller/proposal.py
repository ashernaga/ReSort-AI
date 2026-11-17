import json
import subprocess
import unicodedata
from pathlib import Path, PureWindowsPath

# Support both direct execution and package imports
if __package__:
    from .claude_agent import ask_claude
else:
    from claude_agent import ask_claude


PROJECT_ROOT = Path(__file__).resolve().parent.parent

def _ensure_clean_working_tree() -> None:
    """Reject operations when the Git working tree is not clean."""

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

    except FileNotFoundError as error:
        raise RuntimeError("Git executable was not found.") from error

    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            "Git working-tree check timed out."
        ) from error

    if result.returncode != 0:
        raise RuntimeError(
            "Could not check Git working-tree status:\n"
            + result.stderr.strip()
        )

    if result.stdout.strip():
        raise ValueError(
            "Git working tree is not clean. "
            "Commit or safely stash your changes before applying a patch:\n"
            + result.stdout.strip()
        )

def _check_git_patch(diff: str) -> None:
    """Check whether Git accepts a patch without applying it."""

    try:
        # Send the diff as raw UTF-8 bytes. A text-mode pipe on Windows
        # would rewrite every LF as CRLF and change the patch.
        result = subprocess.run(
            ["git", "apply", "--check", "--"],
            cwd=str(PROJECT_ROOT),
            input=diff.encode("utf-8"),
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
        message = (
            result.stderr.decode("utf-8", errors="replace").strip()
            or result.stdout.decode("utf-8", errors="replace").strip()
        )

        raise ValueError(
            "Git rejected the proposed patch. The context and removed "
            "lines must match the current file contents exactly:\n"
            + message
        )





def _reject_unsafe_text(text: str, label: str) -> None:
    """
    Reject characters that could make displayed text differ from
    the text that would actually be applied.

    Terminal control characters (such as ANSI escapes or a bare
    carriage return) can hide or overwrite lines on screen. Invisible
    and bidirectional Unicode characters can reorder or conceal code.

    Only tab, line feed, and a carriage return immediately followed
    by a line feed are permitted among control characters.
    """

    # Cc: control, Cf: invisible formatting (bidi, zero-width, tags),
    # Cs: surrogates, Zl/Zp: Unicode line and paragraph separators.
    unsafe_categories = {"Cc", "Cf", "Cs", "Zl", "Zp"}

    line_number = 1

    for position, char in enumerate(text):
        if char == "\n":
            line_number += 1
            continue

        if char == "\t":
            continue

        if char == "\r" and text[position + 1:position + 2] == "\n":
            continue

        if unicodedata.category(char) in unsafe_categories:
            raise ValueError(
                f"{label} contains a disallowed control or invisible "
                f"character U+{ord(char):04X} on line {line_number}. "
                "Remove it and use plain visible text."
            )


# Names that may not appear anywhere in a proposed path.
# These hold Git metadata or configuration for Git, editors, and agents.
PROTECTED_NAMES = {
    ".git",
    ".gitmodules",
    ".gitignore",
    ".gitattributes",
    ".vscode",
    ".claude",
    ".agents",
    ".github",
}

# Top-level entries that proposals may not modify. These are the safety
# controller, the scripts that launch it, its tests, and the project
# instructions. Change them by hand, outside the approval workflow.
PROTECTED_TOP_LEVEL = {
    "agent_controller",
    "scripts",
    "tests",
    "claude.md",
}


def _reject_protected_path(parts: list, file_path: str) -> None:
    """Reject paths that proposals are never allowed to modify."""

    folded = [part.casefold() for part in parts]

    if (
        any(part in PROTECTED_NAMES for part in folded)
        or any(part.startswith(".env") for part in folded)
        or (folded and folded[0] in PROTECTED_TOP_LEVEL)
    ):
        raise ValueError(
            f"Protected project path: {file_path}. "
            "Proposals cannot modify this file."
        )


def _validate_project_file(file_path: str) -> Path:
    """Validate that a path identifies a safe, tracked project file."""

    import re

    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("Invalid file path.")

    if "\\" in file_path:
        raise ValueError(
            f"Use forward slashes in file paths: {file_path}"
        )

    # Reject ambiguous or unsafe path components.
    parts = file_path.split("/")

    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Unsafe file path: {file_path}")

    path = Path(file_path)
    windows_path = PureWindowsPath(file_path)

    if (
        path.is_absolute()
        or windows_path.is_absolute()
        or windows_path.drive
    ):
        raise ValueError(f"Absolute paths are not allowed: {file_path}")

    # Protect Git metadata, tool configuration, and the controller itself.
    _reject_protected_path(parts, file_path)

    # Reject Windows-invalid names and alternate data streams.
    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }

    for part in parts:
        if (
            any(ord(char) < 32 or char in '<>:"|?*' for char in part)
            or part.endswith((" ", "."))
        ):
            raise ValueError(
                f"Unsafe Windows path component: {part}"
            )

        device_name = part.split(".", 1)[0].upper()

        if device_name in reserved_names:
            raise ValueError(
                f"Reserved Windows device name: {part}"
            )

    root = PROJECT_ROOT.resolve()
    candidate = root / path

    try:
        # Reject symbolic links in every path component.
        current = root

        for part in parts:
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

        # Repeat the check on the real path, so an alternative spelling
        # (such as a Windows short name) cannot reach a protected file.
        _reject_protected_path(
            list(resolved.relative_to(root).parts),
            file_path,
        )

    except (OSError, RuntimeError) as error:
        raise ValueError(
            f"Could not validate file path: {file_path}"
        ) from error

    # Confirm Git tracks the file and that it is not a submodule.
    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "--stage",
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

    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            f"Could not verify Git tracking: {file_path}"
        ) from error

    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(
            f"File is not tracked by Git: {file_path}"
        )

    for line in result.stdout.splitlines():
        match = re.match(r"^([0-7]{6}) ", line)

        if match and match.group(1) == "160000":
            raise ValueError(
                f"Git submodules cannot be modified: {file_path}"
            )

    return resolved


def _describe_line(lines: list, index: int) -> str:
    """Describe a diff line for an error message."""

    text = lines[index] if index < len(lines) else ""

    return f"diff line {index + 1} ({text[:80]!r})"


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
                "Unsupported diff metadata or malformed file header at "
                + _describe_line(lines, index)
                + '. Each file section must start with "--- a/<path>" '
                'followed by "+++ b/<path>" and then "@@" hunks. '
                "File creation, deletion, renaming, and mode changes "
                "are not allowed."
            )

        old_path = lines[index][4:].split("\t", 1)[0]

        if index + 1 >= len(lines):
            raise ValueError(
                'Incomplete unified diff headers: "--- a/<path>" must '
                'be followed by "+++ b/<path>".'
            )

        if not lines[index + 1].startswith("+++ b/"):
            raise ValueError(
                "Malformed unified diff headers at "
                + _describe_line(lines, index + 1)
                + '. Expected "+++ b/<path>" with the same path as the '
                '"--- a/<path>" line. File creation, deletion, and '
                "renaming are not allowed."
            )

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
                    "Unsupported diff metadata or malformed hunk header "
                    "at "
                    + _describe_line(lines, index)
                    + '. Expected "@@ -start,count +start,count @@". '
                    "Check that the previous hunk's line counts are "
                    "correct."
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
                    raise ValueError(
                        "Incomplete diff hunk: the last @@ header "
                        "declares more lines than the diff contains."
                    )

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
                    raise ValueError(
                        "Invalid unified diff hunk line at "
                        + _describe_line(lines, index)
                        + '. Every hunk line must start with a space, '
                        '"+", or "-".'
                    )

                if (
                    old_seen > old_expected
                    or new_seen > new_expected
                ):
                    raise ValueError(
                        "Diff hunk line counts do not match the @@ "
                        "header near "
                        + _describe_line(lines, index)
                        + "."
                    )

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

    # Everything shown to the user must display exactly as written.
    _reject_unsafe_text(proposal["summary"], "Proposal summary")
    _reject_unsafe_text(proposal["details"], "Proposal details")
    _reject_unsafe_text(diff, "Proposal diff")

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


def _normalize_diff(diff: str) -> str:
    """
    Tidy harmless formatting differences in a diff returned by Claude.

    This runs once, when the proposal is parsed and before it is
    validated. The normalized diff is the one that is displayed,
    fingerprinted, and applied, so the approved text stays exact.

    Changes made:
    - "diff --git" and "index" lines between file sections are removed.
    - Blank lines between file sections are removed.
    - An empty line inside a hunk becomes a blank context line (" ").
    - A missing final newline is added.

    Headers for creation, deletion, renaming, or mode changes are left
    in place so that validation still rejects them.
    """

    import re

    hunk_pattern = re.compile(
        r"^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@"
    )

    lines = diff.split("\n")

    # A trailing newline produces one empty final element.
    if lines and lines[-1] == "":
        lines.pop()

    output = []
    old_left = 0
    new_left = 0

    for line in lines:
        text = line[:-1] if line.endswith("\r") else line
        ending = line[len(text):]

        if old_left > 0 or new_left > 0:
            # Inside a hunk: keep content, repairing empty context lines.
            if text == "":
                line = " " + ending
                old_left -= 1
                new_left -= 1
            elif text.startswith(" "):
                old_left -= 1
                new_left -= 1
            elif text.startswith("+"):
                new_left -= 1
            elif text.startswith("-"):
                old_left -= 1

            output.append(line)
            continue

        if text.startswith("\\"):
            # "\ No newline at end of file" following a completed hunk.
            output.append(line)
            continue

        if (
            text == ""
            or text.startswith("diff --git ")
            or text.startswith("index ")
        ):
            continue

        match = hunk_pattern.match(text)

        if match:
            old_left = int(match.group(1)) if match.group(1) else 1
            new_left = int(match.group(2)) if match.group(2) else 1

        output.append(line)

    if not output:
        return diff

    return "\n".join(output) + "\n"


def _extract_json(raw_response: str) -> str:
    """Strip Markdown fences or surrounding text around a JSON object."""

    text = raw_response.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0].strip()

    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")

        if start != -1 and end > start:
            text = text[start:end + 1]

    return text


def parse_proposal(raw_response: str) -> dict:
    """Parse and validate Claude's JSON proposal."""

    try:
        proposal = json.loads(_extract_json(raw_response))
    except json.JSONDecodeError as error:
        raise ValueError(
            "Claude did not return valid JSON. "
            "The proposal must be plain JSON without Markdown."
        ) from error

    # Tidy the diff before validation, display, and fingerprinting.
    if isinstance(proposal, dict) and isinstance(proposal.get("diff"), str):
        proposal["diff"] = _normalize_diff(proposal["diff"])

    validate_proposal(proposal)

    return proposal

# How many times Claude may try to produce a valid proposal.
MAX_PROPOSAL_ATTEMPTS = 3


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
10. Only modify existing files tracked by Git. Do not create, delete,
    or rename files.
11. Do not propose changes to agent_controller/, scripts/, tests/,
    CLAUDE.md, or configuration such as .gitignore, .vscode, or .env.

RETURN FORMAT:
Return ONLY valid JSON, without Markdown fences or explanations.

Use exactly this structure:
{{
    "summary": "Short description of the proposed change",
    "details": "Explanation and reasoning",
    "files": ["relative/path/to/file.py"],
    "diff": "Unified diff as a JSON string"
}}

The diff must use standard unified diff headers. Start each file
section with "--- a/<path>" and "+++ b/<path>", followed by "@@" hunks.
Do not include "diff --git" or "index" lines.
Context lines must match the current file contents exactly.
Do not claim that changes have been applied.
"""

    print("\nClaude is preparing a proposed change...")

    proposal = None
    last_error = None

    for attempt in range(MAX_PROPOSAL_ATTEMPTS):
        raw_response = ask_claude(prompt)

        try:
            proposal = parse_proposal(raw_response)
            break
        except ValueError as error:
            last_error = error
            print(f"Proposal attempt {attempt + 1} was invalid: {error}")

            prompt += (
                "\n\nYour previous answer was rejected: "
                f"{error}\nReturn ONLY the corrected JSON object."
            )

    if proposal is None:
        raise last_error

    print("Claude proposal received and validated.")

    return proposal