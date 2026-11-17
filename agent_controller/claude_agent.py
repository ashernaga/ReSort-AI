import os
import re
import subprocess
import shutil
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Model names are short identifiers such as "claude-sonnet-5-5" or "sonnet".
# Anything else (spaces, a leading dash) is refused, so the value can never
# be read by the Claude CLI as a different option.
_MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:\[\]-]{0,63}")


def get_claude_model() -> str | None:
    """
    Return the optional CLAUDE_MODEL setting, or None to use the CLI default.

    The value comes from the environment or the project's .env file.
    """

    load_dotenv(PROJECT_ROOT / ".env")

    model = os.getenv("CLAUDE_MODEL", "").strip()

    if not model:
        return None

    if not _MODEL_PATTERN.fullmatch(model):
        raise RuntimeError(
            "CLAUDE_MODEL is not a valid model name. Use a plain "
            "identifier such as claude-sonnet-5-5."
        )

    return model


def ask_claude(prompt: str) -> str:
    claude_path = shutil.which("claude")

    if not claude_path:
        raise RuntimeError(
            "Claude CLI not found in Python PATH. "
            "Restart VS Code and try again."
        )

    command = [
        claude_path,
        "-p",
        prompt,
        "--output-format", "text",
        "--max-turns", "60",
        "--permission-mode", "plan",
    ]

    model = get_claude_model()

    if model:
        command += ["--model", model]
        print(f"Claude model: {model}")

    print(f"Claude executable: {claude_path}")
    print(f"Project directory: {PROJECT_ROOT}")

    try:
        result = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        check=False,
    )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude timed out after 10 minutes.")

    if result.returncode != 0:
        raise RuntimeError(
            f"Claude exited with code: {result.returncode}\n"
            f"STDERR:\n{result.stderr}\n"
            f"STDOUT:\n{result.stdout}"
        )

    return result.stdout.strip()
