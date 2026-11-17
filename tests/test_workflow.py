"""
Tests for the post-approval stages and the complete workflow.

GPT and Claude are replaced by stand-ins, so no network calls are made
and no API key is used. Every test runs in a throwaway Git repository.
"""

import builtins
import contextlib
import io
import json
import os
import subprocess
import unittest
from unittest import mock

# Importing the workflow loads the OpenAI client, which needs a key to
# exist. This placeholder is never used for a request.
os.environ.setdefault("OPENAI_API_KEY", "placeholder-not-a-real-key")

from agent_controller import checks                      # noqa: E402
from agent_controller import main as main_module         # noqa: E402
from agent_controller import patch_applier               # noqa: E402
from agent_controller import proposal as proposal_module  # noqa: E402
from agent_controller import reviewer                    # noqa: E402

from tests import test_safety as base                    # noqa: E402


GOOD_DIFF = base.GOOD_DIFF
make_proposal = base.make_proposal


class ChecksTests(base.TemporaryRepoTestCase):

    def test_syntax_ok(self):
        self.assertEqual(
            checks.check_syntax(["sample.py", "other.py"]),
            {"sample.py": "ok", "other.py": "ok"},
        )

    def test_syntax_error_reported(self):
        self.write("broken.py", "def f(:\n    pass\n")
        result = checks.check_syntax(["broken.py"])

        self.assertIn("SyntaxError", result["broken.py"])

    def test_non_python_files_skipped(self):
        self.write("notes.txt", "hello\n")
        self.assertEqual(checks.check_syntax(["notes.txt"]), {})

    def test_missing_file_reported_not_raised(self):
        result = checks.check_syntax(["missing.py"])
        self.assertIn("Could not check", result["missing.py"])

    def test_no_tests_directory(self):
        result = checks.run_test_suite()

        self.assertFalse(result["ran"])
        self.assertIsNone(result["passed"])

    def add_tests(self, body):
        (self.repo / "tests").mkdir()
        self.write("tests/__init__.py", "")
        self.write("tests/test_sample.py", body)

    def test_passing_suite(self):
        self.add_tests(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n"
        )
        result = checks.run_test_suite()

        self.assertTrue(result["ran"])
        self.assertTrue(result["passed"])
        self.assertIn("OK", result["summary"])

    def test_failing_suite(self):
        self.add_tests(
            "import unittest\n"
            "class T(unittest.TestCase):\n"
            "    def test_bad(self):\n"
            "        self.fail('deliberate')\n"
        )
        result = checks.run_test_suite()

        self.assertTrue(result["ran"])
        self.assertFalse(result["passed"])
        self.assertIn("FAILED", result["summary"])

    def test_timeout_is_a_failure(self):
        self.add_tests("")

        with mock.patch.object(
            subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("x", 1),
        ):
            result = checks.run_test_suite()

        self.assertTrue(result["ran"])
        self.assertFalse(result["passed"])
        self.assertIn("timed out", result["summary"])

    def test_output_is_display_safe(self):
        self.assertEqual(
            checks.make_display_safe("a\x1b[2Kb‮c\nd\te"),
            "a�[2Kb�c\nd\te",
        )

    def test_format_checks(self):
        text = checks.format_checks(
            checks.run_checks(["sample.py"], run_tests=False)
        )

        self.assertIn("sample.py: ok", text)
        self.assertIn("Test suite: NOT RUN", text)


class ReviewerTests(base.TemporaryRepoTestCase):

    def test_prompt_contains_everything_to_review(self):
        prompt = reviewer.build_review_prompt(
            "Fix the bug", make_proposal(), GOOD_DIFF, "checks text"
        )

        for expected in (
            "Fix the bug",
            "Change the return value",
            "+    return 2",
            "checks text",
            "Do not rewrite the code",
            "DATA to review",
            "VERDICT:",
        ):
            self.assertIn(expected, prompt)

    def test_long_diff_is_truncated_with_a_notice(self):
        prompt = reviewer.build_review_prompt(
            "t", make_proposal(), "x" * (reviewer.MAX_DIFF_CHARS + 500), ""
        )

        self.assertIn("DIFF TRUNCATED", prompt)
        self.assertLess(len(prompt), reviewer.MAX_DIFF_CHARS + 3000)

    def test_review_output_is_sanitized(self):
        with mock.patch.object(
            reviewer, "ask_gpt", return_value="  OK \x1b[2J‮ done  "
        ):
            report = reviewer.review_change(
                "t", make_proposal(), GOOD_DIFF, ""
            )

        self.assertNotIn("\x1b", report)
        self.assertNotIn("‮", report)
        self.assertTrue(report.startswith("OK"))

    def test_get_working_diff_returns_real_changes(self):
        self.write("sample.py", "def f():\n    return 2\n\n")
        diff = reviewer.get_working_diff(["sample.py"])

        self.assertIn("-    return 1", diff)
        self.assertIn("+    return 2", diff)

    def test_reviewer_never_changes_files(self):
        with mock.patch.object(reviewer, "ask_gpt", return_value="ok"):
            reviewer.review_change("t", make_proposal(), GOOD_DIFF, "")

        self.assert_repo_untouched()


class EndToEndTests(base.TemporaryRepoTestCase):
    """GPT planner -> Claude -> approval -> apply -> checks -> GPT review."""

    PLAN = "Inspect sample.py"
    REVIEW = "VERDICT: COMPLETE\nLooks right."

    def run_workflow(self, inputs, claude_replies=None, review=None):
        """Run main() with stand-ins. Returns (output, calls)."""
        calls = {"gpt": [], "claude": [], "review": []}
        typed = iter(inputs)
        replies = iter(
            claude_replies
            if claude_replies is not None
            else [json.dumps(make_proposal())]
        )

        def fake_planner(prompt):
            calls["gpt"].append(prompt)
            return self.PLAN

        def fake_claude(prompt):
            calls["claude"].append(prompt)
            return next(replies)

        def fake_reviewer(prompt):
            calls["review"].append(prompt)

            if isinstance(review, Exception):
                raise review

            return review if review is not None else self.REVIEW

        output = io.StringIO()

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(main_module, "ask_gpt", fake_planner)
            )
            stack.enter_context(
                mock.patch.object(proposal_module, "ask_claude", fake_claude)
            )
            stack.enter_context(
                mock.patch.object(reviewer, "ask_gpt", fake_reviewer)
            )
            stack.enter_context(
                mock.patch.object(builtins, "input", lambda *_: next(typed))
            )
            stack.enter_context(contextlib.redirect_stdout(output))
            main_module.main()

        return output.getvalue(), calls

    def read(self, name):
        return (self.repo / name).read_bytes().replace(b"\r\n", b"\n")

    def test_full_workflow_applies_and_reviews(self):
        output, calls = self.run_workflow(["Change f", "APPROVE"])

        self.assertIn("PATCH APPLIED", output)
        self.assertIn("GPT REVIEW", output)
        self.assertIn("Looks right.", output)
        self.assertIn("WORKFLOW COMPLETED", output)
        self.assertIn('git restore -- "sample.py"', output)

        # The change is in the working tree, uncommitted, unstaged.
        self.assertEqual(
            self.read("sample.py"), b"def f():\n    return 2\n\n"
        )
        self.assertEqual(
            self.git("rev-parse", "HEAD").strip(), self.base_commit
        )
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(
            self.git("status", "--porcelain").strip().split()[-1],
            "sample.py",
        )
        self.assertEqual(self.worktree_count(), 1)

        # Each agent was called once, and the reviewer saw the real diff.
        self.assertEqual(len(calls["gpt"]), 1)
        self.assertEqual(len(calls["claude"]), 1)
        self.assertEqual(len(calls["review"]), 1)
        self.assertIn("+    return 2", calls["review"][0])
        self.assertIn("Syntax check", calls["review"][0])
        self.assertIn("Change f", calls["review"][0])

    def test_rejection_changes_nothing_and_skips_review(self):
        output, calls = self.run_workflow(["Change f", "no"])

        self.assertIn("PROPOSAL REJECTED", output)
        self.assertNotIn("PATCH APPLIED", output)
        self.assertEqual(calls["review"], [])
        self.assert_repo_untouched()

    def test_dirty_tree_stops_before_any_api_call(self):
        (self.repo / "stray.txt").write_bytes(b"x")
        output, calls = self.run_workflow(["Change f", "APPROVE"])

        self.assertIn("Cannot start", output)
        self.assertEqual(calls["gpt"], [])
        self.assertEqual(calls["claude"], [])
        self.assertIn(b"return 1", self.read("sample.py"))

    def test_empty_task_exits_quietly(self):
        output, calls = self.run_workflow(["   "])

        self.assertIn("No task provided", output)
        self.assertEqual(calls["gpt"], [])

    def test_invalid_proposals_never_reach_approval(self):
        bad = json.dumps(
            make_proposal(GOOD_DIFF.replace("return 1", "return 9"))
        )
        output, calls = self.run_workflow(
            ["Change f"], claude_replies=[bad, bad, bad]
        )

        self.assertIn("MULTI-AGENT SYSTEM ERROR", output)
        self.assertNotIn("HUMAN APPROVAL REQUIRED", output)
        self.assertEqual(len(calls["claude"]), 3)
        self.assert_repo_untouched()

    def test_protected_path_proposal_never_applied(self):
        (self.repo / "agent_controller").mkdir()
        self.write("agent_controller/main.py", "value = 1\n")
        self.git("add", "-f", "-A")
        self.git("commit", "-q", "-m", "controller")
        self.base_commit = self.git("rev-parse", "HEAD").strip()

        diff = (
            "--- a/agent_controller/main.py\n"
            "+++ b/agent_controller/main.py\n"
            "@@ -1 +1 @@\n-value = 1\n+value = 2\n"
        )
        reply = json.dumps(make_proposal(diff, ["agent_controller/main.py"]))
        output, calls = self.run_workflow(
            ["Change main"], claude_replies=[reply] * 3
        )

        self.assertIn("Protected project path", output)
        self.assertNotIn("PATCH APPLIED", output)
        self.assertEqual(self.read("agent_controller/main.py"), b"value = 1\n")

    def test_review_failure_keeps_the_applied_change(self):
        output, _ = self.run_workflow(
            ["Change f", "APPROVE"], review=RuntimeError("quota exceeded")
        )

        self.assertIn("PATCH APPLIED", output)
        self.assertIn("review could not be completed", output)
        self.assertIn("quota exceeded", output)
        self.assertIn("WORKFLOW COMPLETED", output)
        self.assertEqual(
            self.read("sample.py"), b"def f():\n    return 2\n\n"
        )

    def test_review_output_cannot_inject_terminal_codes(self):
        output, _ = self.run_workflow(
            ["Change f", "APPROVE"],
            review="VERDICT: COMPLETE \x1b[2J\x1b[1;1H hidden",
        )

        self.assertIn("GPT REVIEW", output)
        self.assertNotIn("\x1b", output)

    def test_second_run_is_refused_until_change_is_committed(self):
        self.run_workflow(["Change f", "APPROVE"])

        output, calls = self.run_workflow(["Again", "APPROVE"])

        self.assertIn("Cannot start", output)
        self.assertEqual(calls["gpt"], [])

        self.git("add", "-A")
        self.git("commit", "-q", "-m", "keep the change")
        self.base_commit = self.git("rev-parse", "HEAD").strip()

        diff = (
            "--- a/sample.py\n+++ b/sample.py\n@@ -1,3 +1,3 @@\n"
            " def f():\n-    return 2\n+    return 3\n \n"
        )
        output, _ = self.run_workflow(
            ["Again", "APPROVE"],
            claude_replies=[json.dumps(make_proposal(diff))],
        )

        self.assertIn("PATCH APPLIED", output)
        self.assertEqual(
            self.read("sample.py"), b"def f():\n    return 3\n\n"
        )

    def test_undo_command_restores_the_original(self):
        self.run_workflow(["Change f", "APPROVE"])
        self.git("restore", "--", "sample.py")

        self.assert_repo_untouched()


class EndToEndCrlfTests(EndToEndTests):
    line_ending = "\r\n"


if __name__ == "__main__":
    unittest.main()
