"""
Safety tests for the agent controller.

Every test runs against a throwaway Git repository in a temporary
directory. The real project is never used as the patch target.

Run from the project root:

    venv\\Scripts\\python.exe -B -m unittest discover -s tests -t . -v
"""

import builtins
import contextlib
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_controller import approval
from agent_controller import patch_applier
from agent_controller import proposal as proposal_module


GOOD_DIFF = (
    "--- a/sample.py\n"
    "+++ b/sample.py\n"
    "@@ -1,3 +1,3 @@\n"
    " def f():\n"
    "-    return 1\n"
    "+    return 2\n"
    " \n"
)


def make_proposal(diff=GOOD_DIFF, files=("sample.py",)):
    return {
        "summary": "Change the return value",
        "details": "Test proposal",
        "files": list(files),
        "diff": diff,
    }


class TemporaryRepoTestCase(unittest.TestCase):
    """Create a temporary repository and point the controller at it."""

    # Line ending used for files in the working tree.
    line_ending = "\n"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(
            prefix="trash_ml_tests_",
            ignore_cleanup_errors=True,
        )
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name).resolve() / "repo"
        self.repo.mkdir()

        self.git("init", "-q", ".")
        self.git("config", "user.email", "tests@example.invalid")
        self.git("config", "user.name", "tests")
        self.git(
            "config",
            "core.autocrlf",
            "true" if self.line_ending == "\r\n" else "false",
        )

        self.write("sample.py", "def f():\n    return 1\n\n")
        self.write("other.py", "y = 1\n")
        self.write(".gitignore", "__pycache__/\n*.ignored\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "base")
        self.base_commit = self.git("rev-parse", "HEAD").strip()

        # Redirect both modules to the temporary repository.
        for module in (proposal_module, patch_applier):
            patcher = mock.patch.object(module, "PROJECT_ROOT", self.repo)
            patcher.start()
            self.addCleanup(patcher.stop)

        self.assertEqual(proposal_module.PROJECT_ROOT, self.repo)
        self.assertEqual(patch_applier.PROJECT_ROOT, self.repo)

    # Helpers

    def git(self, *args):
        result = subprocess.run(
            ["git", *args],
            cwd=str(self.repo),
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            result.stderr.decode("utf-8", errors="replace"),
        )
        return result.stdout.decode("utf-8", errors="replace")

    def write(self, name, text):
        data = text.replace("\n", self.line_ending).encode("utf-8")
        (self.repo / name).write_bytes(data)

    def receipt(self, proposal, **overrides):
        receipt = {
            "approved": True,
            "diff_hash": patch_applier.calculate_diff_hash(
                proposal["diff"]
            ),
            "baseline_commit": self.base_commit,
        }
        receipt.update(overrides)
        return receipt

    def worktree_count(self):
        output = self.git("worktree", "list", "--porcelain")
        return sum(
            1 for line in output.splitlines()
            if line.startswith("worktree ")
        )

    def assert_repo_untouched(self):
        self.assertEqual(
            self.git("status", "--porcelain", "--untracked-files=all"),
            "",
        )
        self.assertEqual(
            self.git("rev-parse", "HEAD").strip(),
            self.base_commit,
        )
        self.assertEqual(self.worktree_count(), 1)
        self.assertIn(
            b"return 1",
            (self.repo / "sample.py").read_bytes(),
        )


class ValidProposalTests(TemporaryRepoTestCase):
    """A correct proposal passes every stage (LF working files)."""

    def test_working_files_use_expected_line_ending(self):
        data = (self.repo / "sample.py").read_bytes()
        self.assertEqual(b"\r\n" in data, self.line_ending == "\r\n")

    def test_validate_proposal(self):
        self.assertTrue(proposal_module.validate_proposal(make_proposal()))

    def test_dry_run_validation(self):
        proposal = make_proposal()
        self.assertTrue(
            patch_applier.validate_patch_application(
                proposal, self.receipt(proposal)
            )
        )
        self.assert_repo_untouched()

    def test_temporary_worktree_verification(self):
        proposal = make_proposal()
        result = patch_applier.verify_patch_in_temporary_worktree(
            proposal, self.receipt(proposal)
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["changed_files"], ["sample.py"])
        self.assertEqual(result["baseline_commit"], self.base_commit)
        self.assert_repo_untouched()

    def test_git_receives_exact_diff_bytes(self):
        """Regression: the diff must not be rewritten on its way to Git."""
        real_run = subprocess.run
        seen = []

        def recording_run(command, *args, **kwargs):
            if command[:2] == ["git", "apply"]:
                seen.append(kwargs.get("input"))
            return real_run(command, *args, **kwargs)

        proposal = make_proposal()

        with mock.patch.object(subprocess, "run", recording_run):
            patch_applier.verify_patch_in_temporary_worktree(
                proposal, self.receipt(proposal)
            )

        self.assertTrue(seen)

        for sent in seen:
            self.assertEqual(sent, GOOD_DIFF.encode("utf-8"))


class ValidProposalCrlfTests(ValidProposalTests):
    """The same checks with CRLF working files (Windows checkout)."""

    line_ending = "\r\n"


class ReceiptTests(TemporaryRepoTestCase):

    def verify(self, proposal, receipt):
        return patch_applier.verify_patch_in_temporary_worktree(
            proposal, receipt
        )

    def test_not_approved(self):
        proposal = make_proposal()

        for value in (False, None, "True", 1):
            with self.subTest(approved=value):
                with self.assertRaises(ValueError):
                    self.verify(
                        proposal, self.receipt(proposal, approved=value)
                    )

    def test_wrong_fingerprint(self):
        proposal = make_proposal()

        with self.assertRaises(ValueError):
            self.verify(
                proposal, self.receipt(proposal, diff_hash="0" * 64)
            )

    def test_diff_modified_after_approval(self):
        approved = make_proposal()
        modified = make_proposal(
            GOOD_DIFF.replace("return 2", "return 3")
        )

        with self.assertRaises(ValueError):
            self.verify(modified, self.receipt(approved))

    def test_wrong_baseline(self):
        proposal = make_proposal()

        with self.assertRaises(ValueError):
            self.verify(
                proposal,
                self.receipt(proposal, baseline_commit="f" * 40),
            )

    def test_invalid_receipt_types(self):
        proposal = make_proposal()

        for receipt in (None, "APPROVE", []):
            with self.subTest(receipt=receipt):
                with self.assertRaises(ValueError):
                    self.verify(proposal, receipt)

    def tearDown(self):
        self.assert_repo_untouched()


class PathValidationTests(TemporaryRepoTestCase):

    BAD_PATHS = [
        "../outside.py",
        "sub/../sample.py",
        "./sample.py",
        ".git/config",
        ".GIT/config",
        ".gitignore",
        ".gitmodules",
        "C:/Windows/win.ini",
        "/etc/passwd",
        "sub\\x.py",
        "NUL",
        "con.py",
        "sample.py:stream",
        "sample.py ",
        "sample.py.",
        "untracked.py",
        "missing.py",
        "",
    ]

    def test_bad_paths_rejected(self):
        (self.repo / "untracked.py").write_bytes(b"x = 1\n")

        for path in self.BAD_PATHS:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    proposal_module.validate_proposal(
                        make_proposal(
                            GOOD_DIFF.replace("sample.py", path),
                            [path],
                        )
                    )

    def test_non_string_path_rejected(self):
        with self.assertRaises(ValueError):
            proposal_module.validate_proposal(
                make_proposal(GOOD_DIFF, [None])
            )


class DiffStructureTests(TemporaryRepoTestCase):

    def assert_rejected(self, proposal):
        with self.assertRaises(ValueError):
            proposal_module.validate_proposal(proposal)

    def test_declared_files_must_match_diff(self):
        self.assert_rejected(
            make_proposal(GOOD_DIFF, ["sample.py", "other.py"])
        )
        self.assert_rejected(make_proposal(GOOD_DIFF, ["other.py"]))

    def test_duplicate_declared_file(self):
        self.assert_rejected(
            make_proposal(GOOD_DIFF, ["sample.py", "sample.py"])
        )

    def test_patch_that_does_not_apply(self):
        self.assert_rejected(
            make_proposal(GOOD_DIFF.replace("return 1", "return 9"))
        )

    def test_file_creation(self):
        self.assert_rejected(
            make_proposal(
                "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x = 1\n",
                ["new.py"],
            )
        )

    def test_file_deletion(self):
        self.assert_rejected(
            make_proposal(
                "--- a/other.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-y = 1\n",
                ["other.py"],
            )
        )

    def test_rename(self):
        self.assert_rejected(
            make_proposal(
                GOOD_DIFF.replace("+++ b/sample.py", "+++ b/other.py")
            )
        )

    def test_wrong_hunk_counts(self):
        self.assert_rejected(
            make_proposal(GOOD_DIFF.replace("-1,3 +1,3", "-1,2 +1,3"))
        )

    def test_missing_or_extra_fields(self):
        proposal = make_proposal()
        self.assert_rejected({**proposal, "extra": 1})
        proposal.pop("details")
        self.assert_rejected(proposal)

    def test_empty_diff(self):
        self.assert_rejected(make_proposal(""))

    def tearDown(self):
        self.assert_repo_untouched()


class DirtyWorkingTreeTests(TemporaryRepoTestCase):

    def assert_rejected(self):
        proposal = make_proposal()

        with self.assertRaises(ValueError):
            patch_applier.validate_patch_application(
                proposal, self.receipt(proposal)
            )

        with self.assertRaises(ValueError):
            patch_applier.verify_patch_in_temporary_worktree(
                proposal, self.receipt(proposal)
            )

        self.assertEqual(self.worktree_count(), 1)

    def test_untracked_file(self):
        (self.repo / "stray.txt").write_bytes(b"x")
        self.assert_rejected()

    def test_unstaged_change(self):
        self.write("other.py", "y = 5\n")
        self.assert_rejected()

    def test_staged_change(self):
        self.write("other.py", "y = 5\n")
        self.git("add", "other.py")
        self.assert_rejected()


class WorktreeCleanupTests(TemporaryRepoTestCase):

    def test_cleanup_after_failure_inside_worktree(self):
        real_run_git = patch_applier._run_git

        def failing_run_git(args, cwd, input_text=None, timeout=30):
            if args[:1] == ["apply"] and "--check" not in args:
                return subprocess.CompletedProcess(
                    args, 1, "", "simulated failure"
                )

            return real_run_git(args, cwd, input_text, timeout)

        proposal = make_proposal()

        with mock.patch.object(
            patch_applier, "_run_git", failing_run_git
        ):
            with self.assertRaises(RuntimeError):
                patch_applier.verify_patch_in_temporary_worktree(
                    proposal, self.receipt(proposal)
                )

        self.assert_repo_untouched()


class ApprovalPromptTests(TemporaryRepoTestCase):

    def ask(self, typed, proposal=None):
        with mock.patch.object(builtins, "input", lambda *_: typed):
            with contextlib.redirect_stdout(io.StringIO()):
                return approval.request_approval(
                    proposal or make_proposal()
                )

    def test_exact_approve_creates_receipt(self):
        receipt = self.ask("APPROVE")

        self.assertEqual(
            receipt,
            {
                "approved": True,
                "diff_hash": patch_applier.calculate_diff_hash(GOOD_DIFF),
                "baseline_commit": self.base_commit,
            },
        )

    def test_anything_else_is_rejected(self):
        for typed in ("approve", "Approve", "yes", "y", "", "APPROVE!"):
            with self.subTest(typed=typed):
                self.assertIsNone(self.ask(typed))

    def test_invalid_proposal_is_never_shown_for_approval(self):
        bad = make_proposal(GOOD_DIFF.replace("return 1", "return 9"))
        self.assertIsNone(self.ask("APPROVE", bad))

    def test_dirty_tree_blocks_approval(self):
        (self.repo / "stray.txt").write_bytes(b"x")
        self.assertIsNone(self.ask("APPROVE"))


if __name__ == "__main__":
    unittest.main()
