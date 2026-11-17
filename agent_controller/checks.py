"""
Automated checks that run after an approved patch has been applied.

The checks only report. They never modify or undo the change.
"""

import ast
import subprocess
import sys
import unicodedata

if __package__:
    from . import patch_applier
else:
    import patch_applier

TEST_TIMEOUT_SECONDS = 900
OUTPUT_TAIL_LINES = 40


def make_display_safe(text: str) -> str:
    """Replace control and invisible characters so text prints safely."""

    unsafe_categories = {"Cc", "Cf", "Cs", "Zl", "Zp"}
    cleaned = []

    for char in text:
        if char in "\n\t":
            cleaned.append(char)
        elif unicodedata.category(char) in unsafe_categories:
            cleaned.append("�")
        else:
            cleaned.append(char)

    return "".join(cleaned)


def check_syntax(changed_files: list) -> dict:
    """Parse every changed Python file. Returns {file: 'ok' or error}."""

    results = {}

    for file_path in changed_files:
        if not file_path.endswith(".py"):
            continue

        full_path = patch_applier.PROJECT_ROOT / file_path

        try:
            ast.parse(full_path.read_bytes(), filename=file_path)
            results[file_path] = "ok"
        except SyntaxError as error:
            results[file_path] = (
                f"SyntaxError: {error.msg} (line {error.lineno})"
            )
        except (OSError, ValueError) as error:
            results[file_path] = f"Could not check: {error}"

    return results


def run_test_suite() -> dict:
    """
    Run the project's unittest suite, if it has one.

    Returns {'ran': bool, 'passed': bool or None, 'summary': str}.
    """

    root = patch_applier.PROJECT_ROOT

    if not (root / "tests").is_dir():
        return {
            "ran": False,
            "passed": None,
            "summary": "No tests directory found; no tests were run.",
        }

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-t",
                ".",
            ],
            cwd=str(root),
            capture_output=True,
            timeout=TEST_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ran": True,
            "passed": False,
            "summary": (
                f"Test run timed out after {TEST_TIMEOUT_SECONDS} seconds."
            ),
        }

    output = (
        result.stdout.decode("utf-8", errors="replace")
        + result.stderr.decode("utf-8", errors="replace")
    )
    tail = "\n".join(output.strip().splitlines()[-OUTPUT_TAIL_LINES:])

    return {
        "ran": True,
        "passed": result.returncode == 0,
        "summary": make_display_safe(tail),
    }


def run_checks(changed_files: list, run_tests: bool = True) -> dict:
    """Run syntax checks and, optionally, the test suite."""

    return {
        "syntax": check_syntax(changed_files),
        "tests": (
            run_test_suite()
            if run_tests
            else {
                "ran": False,
                "passed": None,
                "summary": "Test run was skipped.",
            }
        ),
    }


def format_checks(checks: dict) -> str:
    """Render check results as plain text for the user and the reviewer."""

    lines = ["Syntax check of changed Python files:"]

    if checks["syntax"]:
        for file_path, outcome in checks["syntax"].items():
            lines.append(f"  {file_path}: {outcome}")
    else:
        lines.append("  (no Python files were changed)")

    tests = checks["tests"]

    if not tests["ran"]:
        status = "NOT RUN"
    elif tests["passed"]:
        status = "PASSED"
    else:
        status = "FAILED"

    lines.append(f"Test suite: {status}")
    lines.append(tests["summary"])

    return "\n".join(lines)
