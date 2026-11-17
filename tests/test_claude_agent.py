"""
Tests for how the Claude CLI is invoked. No real Claude process is run.
"""

import contextlib
import io
import subprocess
import unittest
from unittest import mock

from agent_controller import claude_agent


class ClaudeInvocationTests(unittest.TestCase):

    def run_ask(self, model=None, returncode=0, stdout="reply"):
        """Call ask_claude with a fake CLI. Returns (reply, command)."""
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(
                command, returncode, stdout=stdout + "\n", stderr=""
            )

        env = {"CLAUDE_MODEL": model} if model is not None else {}

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(
                    claude_agent.shutil, "which", return_value="claude"
                )
            )
            stack.enter_context(
                mock.patch.object(claude_agent.subprocess, "run", fake_run)
            )
            # Ignore any real .env so the test sees only the given value.
            stack.enter_context(
                mock.patch.object(claude_agent, "load_dotenv")
            )
            stack.enter_context(
                mock.patch.dict(claude_agent.os.environ, env, clear=False)
            )

            if model is None:
                claude_agent.os.environ.pop("CLAUDE_MODEL", None)

            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            reply = claude_agent.ask_claude("the prompt")

        return reply, seen

    def test_always_runs_in_plan_mode(self):
        _, seen = self.run_ask()
        command = seen["command"]

        index = command.index("--permission-mode")
        self.assertEqual(command[index + 1], "plan")

    def test_never_skips_permissions(self):
        for model in (None, "claude-sonnet-5-5"):
            with self.subTest(model=model):
                _, seen = self.run_ask(model=model)

                self.assertFalse(
                    any("dangerously" in part for part in seen["command"])
                )
                self.assertFalse(
                    any("skip-permissions" in part for part in seen["command"])
                )

    def test_prompt_is_passed_as_one_argument(self):
        _, seen = self.run_ask()
        command = seen["command"]

        self.assertEqual(command[command.index("-p") + 1], "the prompt")
        self.assertNotIn("shell", seen["kwargs"])

    def test_default_model_when_not_configured(self):
        _, seen = self.run_ask()

        self.assertNotIn("--model", seen["command"])

    def test_configured_model_is_passed(self):
        _, seen = self.run_ask(model="claude-sonnet-5-5")
        command = seen["command"]

        self.assertEqual(
            command[command.index("--model") + 1], "claude-sonnet-5-5"
        )

    def test_blank_model_means_default(self):
        _, seen = self.run_ask(model="   ")

        self.assertNotIn("--model", seen["command"])

    def test_invalid_model_names_are_refused(self):
        for bad in (
            "--dangerously-skip-permissions",
            "-x",
            "sonnet --foo",
            "a b",
            "model;rm",
            "x" * 80,
            "\x1b[2K",
        ):
            with self.subTest(model=bad):
                with self.assertRaises(RuntimeError):
                    self.run_ask(model=bad)

    def test_valid_model_names_accepted(self):
        for good in ("sonnet", "opus", "claude-opus-5-5", "claude-x.1:y"):
            with self.subTest(model=good):
                _, seen = self.run_ask(model=good)

                self.assertIn(good, seen["command"])

    def test_nonzero_exit_raises_with_output(self):
        with self.assertRaises(RuntimeError) as caught:
            self.run_ask(returncode=1, stdout="needs credits")

        self.assertIn("needs credits", str(caught.exception))

    def test_reply_is_returned_stripped(self):
        reply, _ = self.run_ask(stdout="  hello  ")

        self.assertEqual(reply, "hello")


if __name__ == "__main__":
    unittest.main()
