import subprocess
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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
