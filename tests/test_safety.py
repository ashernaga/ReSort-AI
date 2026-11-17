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
from agent_controller import receipts


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
        """Build a receipt as the approval step would, then sign it."""
        receipt = {
            "approved": True,
            "diff_hash": patch_applier.calculate_diff_hash(
                proposal["diff"]
            ),
            "baseline_commit": self.base_commit,
        }
        receipt.update(overrides)
        return receipts.sign_receipt(receipt)

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


class SignedReceiptTests(TemporaryRepoTestCase):
    """Receipts must come from the approval step and be used once."""

    def test_unsigned_receipt_rejected(self):
        proposal = make_proposal()
        unsigned = {
            "approved": True,
            "diff_hash": patch_applier.calculate_diff_hash(GOOD_DIFF),
            "baseline_commit": self.base_commit,
        }

        for stage in (
            patch_applier.validate_patch_application,
            patch_applier.verify_patch_in_temporary_worktree,
            patch_applier.apply_approved_patch,
        ):
            with self.subTest(stage=stage.__name__):
                with self.assertRaises(ValueError) as caught:
                    stage(proposal, unsigned)

                self.assertIn("not signed", str(caught.exception))

    def test_forged_signature_rejected(self):
        proposal = make_proposal()
        forged = {**self.receipt(proposal), "signature": "0" * 64}

        with self.assertRaises(ValueError):
            patch_applier.apply_approved_patch(proposal, forged)

    def test_receipt_edited_after_signing_rejected(self):
        proposal = make_proposal()
        other = make_proposal(GOOD_DIFF.replace("return 2", "return 3"))
        edited = {
            **self.receipt(proposal),
            "diff_hash": patch_applier.calculate_diff_hash(other["diff"]),
        }

        with self.assertRaises(ValueError):
            patch_applier.apply_approved_patch(other, edited)

    def test_receipt_from_another_session_rejected(self):
        proposal = make_proposal()
        receipt = self.receipt(proposal)

        with mock.patch.object(receipts, "_SESSION_KEY", b"x" * 32):
            with self.assertRaises(ValueError):
                patch_applier.apply_approved_patch(proposal, receipt)

    def test_receipt_cannot_be_used_twice(self):
        receipt = self.receipt(make_proposal())

        receipts.consume_receipt(receipt)

        with self.assertRaises(ValueError) as caught:
            receipts.consume_receipt(receipt)

        self.assertIn("already been used", str(caught.exception))

    def test_non_dict_has_no_valid_signature(self):
        for value in (None, "sig", [], 5):
            self.assertFalse(receipts.verify_signature(value))

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


class ProtectedPathTests(TemporaryRepoTestCase):
    """Proposals cannot modify the controller or tool configuration."""

    PROTECTED = [
        "agent_controller/main.py",
        "Agent_Controller/main.py",
        "scripts/run_agent.ps1",
        "tests/test_safety.py",
        "CLAUDE.md",
        "claude.md",
        ".gitattributes",
        ".vscode/settings.json",
        ".claude/settings.json",
        ".github/workflows/ci.yml",
        "sub/.vscode/settings.json",
        ".env.example",
    ]

    ALLOWED = [
        "sample.py",
        "sub/scripts/tool.py",
        "sub/tests/helper.py",
        "environment.py",
    ]

    def setUp(self):
        super().setUp()

        for path in self.PROTECTED + self.ALLOWED:
            target = self.repo / path

            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                self.write(path, "value = 1\n")

        self.git("add", "-A", "-f")
        self.git("commit", "-q", "-m", "more files")
        self.base_commit = self.git("rev-parse", "HEAD").strip()

    def test_protected_paths_rejected(self):
        for path in self.PROTECTED:
            with self.subTest(path=path):
                with self.assertRaises(ValueError) as caught:
                    proposal_module._validate_project_file(path)

                self.assertIn(
                    "Protected project path", str(caught.exception)
                )

    def test_protected_path_rejected_in_full_proposal(self):
        diff = (
            "--- a/agent_controller/main.py\n"
            "+++ b/agent_controller/main.py\n"
            "@@ -1 +1 @@\n"
            "-value = 1\n"
            "+value = 2\n"
        )

        with self.assertRaises(ValueError) as caught:
            proposal_module.validate_proposal(
                make_proposal(diff, ["agent_controller/main.py"])
            )

        self.assertIn("Protected project path", str(caught.exception))

    def test_similar_unprotected_paths_allowed(self):
        for path in self.ALLOWED:
            with self.subTest(path=path):
                proposal_module._validate_project_file(path)

    def tearDown(self):
        self.assert_repo_untouched()


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


class DisplaySpoofingTests(TemporaryRepoTestCase):
    """Text shown for approval must display exactly as written."""

    UNSAFE = {
        "ANSI escape": "\x1b[2K\x1b[1A",
        "bare carriage return": "\rhidden",
        "backspace": "\x08",
        "form feed": "\x0c",
        "delete": "\x7f",
        "C1 control sequence introducer": "\x9b2K",
        "next line": "\x85",
        "right-to-left override": "‮",
        "left-to-right isolate": "⁦",
        "zero-width space": "​",
        "byte order mark": "﻿",
        "line separator": " ",
        "paragraph separator": " ",
        "tag character": "\U000e0041",
    }

    def test_unsafe_characters_in_diff_rejected(self):
        for name, text in self.UNSAFE.items():
            with self.subTest(name=name):
                diff = GOOD_DIFF.replace(
                    "return 2", "return 2  # " + text
                )

                with self.assertRaises(ValueError) as caught:
                    proposal_module.validate_proposal(make_proposal(diff))

                self.assertIn("Proposal diff", str(caught.exception))

    def test_unsafe_characters_in_summary_and_details_rejected(self):
        for field in ("summary", "details"):
            with self.subTest(field=field):
                proposal = make_proposal()
                proposal[field] = "Harmless \x1b[8m hidden text"

                with self.assertRaises(ValueError):
                    proposal_module.validate_proposal(proposal)

    def test_error_reports_code_point_and_line(self):
        diff = GOOD_DIFF.replace("return 2", "return 2 \x1b[0m")

        with self.assertRaises(ValueError) as caught:
            proposal_module.validate_proposal(make_proposal(diff))

        self.assertIn("U+001B on line 6", str(caught.exception))

    def test_unsafe_proposal_is_never_displayed(self):
        diff = GOOD_DIFF.replace("return 2", "return 2 \x1b[2K")
        output = io.StringIO()

        with mock.patch.object(builtins, "input", lambda *_: "APPROVE"):
            with contextlib.redirect_stdout(output):
                receipt = approval.request_approval(make_proposal(diff))

        self.assertIsNone(receipt)
        self.assertNotIn("\x1b", output.getvalue())

    def test_visible_unicode_and_tabs_accepted(self):
        diff = (
            "--- a/other.py\n"
            "+++ b/other.py\n"
            "@@ -1 +1 @@\n"
            "-y = 1\n"
            "+y = 'café 中文 \U0001f600'\t# tab\n"
        )
        proposal = make_proposal(diff, ["other.py"])
        proposal["summary"] = "Résumé 中文"

        self.assertTrue(proposal_module.validate_proposal(proposal))

    def test_crlf_line_endings_accepted_by_text_check(self):
        proposal_module._reject_unsafe_text("a\r\nb\r\n", "Text")

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

    def test_ignored_file_does_not_block(self):
        """Ignored files (venv, .env, models) are expected to exist."""
        (self.repo / "junk.ignored").write_bytes(b"x")
        proposal = make_proposal()

        self.assertTrue(
            patch_applier.validate_patch_application(
                proposal, self.receipt(proposal)
            )
        )

        result = patch_applier.verify_patch_in_temporary_worktree(
            proposal, self.receipt(proposal)
        )

        self.assertTrue(result["verified"])
        self.assertEqual(self.worktree_count(), 1)

    def test_unstaged_change(self):
        self.write("other.py", "y = 5\n")
        self.assert_rejected()

    def test_staged_change(self):
        self.write("other.py", "y = 5\n")
        self.git("add", "other.py")
        self.assert_rejected()


class ApplyApprovedPatchTests(TemporaryRepoTestCase):
    """Real application: exact result, verification, and rollback."""

    def apply(self, proposal=None):
        proposal = proposal or make_proposal()

        return patch_applier.apply_approved_patch(
            proposal, self.receipt(proposal)
        )

    def read(self, name):
        return (self.repo / name).read_bytes().replace(b"\r\n", b"\n")

    def test_applies_exact_diff_and_leaves_it_uncommitted(self):
        result = self.apply()

        self.assertTrue(result["applied"])
        self.assertEqual(result["changed_files"], ["sample.py"])
        self.assertEqual(
            self.read("sample.py"), b"def f():\n    return 2\n\n"
        )
        self.assertEqual(self.read("other.py"), b"y = 1\n")
        self.assertEqual(
            self.git("rev-parse", "HEAD").strip(), self.base_commit
        )
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(
            self.git("diff", "--name-only").strip(), "sample.py"
        )
        self.assertEqual(self.worktree_count(), 1)
        self.assertEqual(
            result["undo_command"], 'git restore -- "sample.py"'
        )

    def test_result_matches_the_sandbox_hashes(self):
        proposal = make_proposal()
        receipt = self.receipt(proposal)
        sandbox = patch_applier.verify_patch_in_temporary_worktree(
            proposal, receipt
        )
        result = patch_applier.apply_approved_patch(proposal, receipt)

        self.assertEqual(result["file_hashes"], sandbox["file_hashes"])
        self.assertEqual(
            patch_applier._hash_file(self.repo, "sample.py"),
            sandbox["file_hashes"]["sample.py"],
        )

    def test_receipt_is_spent_after_application(self):
        proposal = make_proposal()
        receipt = self.receipt(proposal)

        patch_applier.apply_approved_patch(proposal, receipt)
        self.git("restore", "--", "sample.py")

        with self.assertRaises(ValueError) as caught:
            patch_applier.apply_approved_patch(proposal, receipt)

        self.assertIn("already been used", str(caught.exception))
        self.assertIn(b"return 1", self.read("sample.py"))

    def test_rejected_before_any_change(self):
        """Every pre-application failure leaves the project untouched."""
        proposal = make_proposal()
        good = self.receipt(proposal)
        cases = {
            "not approved": self.receipt(proposal, approved=False),
            "wrong hash": self.receipt(proposal, diff_hash="0" * 64),
            "wrong baseline": self.receipt(
                proposal, baseline_commit="f" * 40
            ),
            "unsigned": {
                k: v for k, v in good.items() if k != "signature"
            },
        }

        for name, receipt in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    patch_applier.apply_approved_patch(proposal, receipt)

                self.assert_repo_untouched()

    def test_dirty_tree_blocks_application(self):
        (self.repo / "stray.txt").write_bytes(b"x")

        with self.assertRaises(ValueError):
            self.apply()

        self.assertIn(b"return 1", self.read("sample.py"))

    def test_wrong_result_is_rolled_back(self):
        """If the result differs from the sandbox, the patch is undone."""
        real_verify = patch_applier._verify_applied_result

        def tampered(baseline, files, hashes):
            return real_verify(
                baseline, files, {name: "0" * 40 for name in files}
            )

        with mock.patch.object(
            patch_applier, "_verify_applied_result", tampered
        ):
            with self.assertRaises(RuntimeError) as caught:
                self.apply()

        self.assertIn("failed verification", str(caught.exception))
        self.assertIn("rolled back", str(caught.exception))
        self.assert_repo_untouched()

    def test_rollback_keeps_unrelated_edits(self):
        """Reverse-applying only undoes the patch, not other changes."""
        proposal = make_proposal()
        real_verify = patch_applier._verify_applied_result

        def tampered(baseline, files, hashes):
            # Someone edits another file while the patch is applied.
            self.write("other.py", "y = 99\n")

            raise RuntimeError("simulated verification failure")

        with mock.patch.object(
            patch_applier, "_verify_applied_result", tampered
        ):
            with self.assertRaises(RuntimeError) as caught:
                self.apply(proposal)

        self.assertIn(b"return 1", self.read("sample.py"))
        self.assertEqual(self.read("other.py"), b"y = 99\n")
        self.assertIn("rolled back", str(caught.exception))
        self.assertIn("were not made by this patch", str(caught.exception))

    def test_failed_rollback_reports_manual_command(self):
        proposal = make_proposal()

        def tampered(baseline, files, hashes):
            # Someone changes the patched file, so it cannot be reversed.
            self.write("sample.py", "def f():\n    return 42\n\n")

            raise RuntimeError("simulated verification failure")

        with mock.patch.object(
            patch_applier, "_verify_applied_result", tampered
        ):
            with self.assertRaises(RuntimeError) as caught:
                self.apply(proposal)

        self.assertIn("ROLLBACK FAILED", str(caught.exception))
        self.assertIn('git restore -- "sample.py"', str(caught.exception))
        self.assertIn(b"return 42", self.read("sample.py"))

    def test_failed_apply_changes_nothing(self):
        real_run_git = patch_applier._run_git

        def failing(args, cwd, input_text=None, timeout=30):
            if (
                args[:2] == ["apply", "--"]
                and cwd == patch_applier.PROJECT_ROOT
            ):
                return subprocess.CompletedProcess(
                    args, 1, "", "simulated failure"
                )

            return real_run_git(args, cwd, input_text, timeout)

        with mock.patch.object(patch_applier, "_run_git", failing):
            with self.assertRaises(RuntimeError) as caught:
                self.apply()

        self.assertIn("Nothing was changed", str(caught.exception))
        self.assert_repo_untouched()

    def test_extra_file_change_is_detected(self):
        """A change outside the approved list fails verification."""
        proposal = make_proposal()
        real_apply = patch_applier._run_git

        def sneaky(args, cwd, input_text=None, timeout=30):
            result = real_apply(args, cwd, input_text, timeout)

            if (
                args[:2] == ["apply", "--"]
                and cwd == patch_applier.PROJECT_ROOT
                and result.returncode == 0
            ):
                self.write("other.py", "y = 2\n")

            return result

        with mock.patch.object(patch_applier, "_run_git", sneaky):
            with self.assertRaises(RuntimeError) as caught:
                self.apply(proposal)

        self.assertIn("failed verification", str(caught.exception))
        self.assertIn("differ from the approved list", str(caught.exception))

    def test_new_file_is_detected(self):
        real_run_git = patch_applier._run_git

        def sneaky(args, cwd, input_text=None, timeout=30):
            result = real_run_git(args, cwd, input_text, timeout)

            if (
                args[:2] == ["apply", "--"]
                and cwd == patch_applier.PROJECT_ROOT
                and result.returncode == 0
            ):
                (self.repo / "created.txt").write_bytes(b"x")

            return result

        with mock.patch.object(patch_applier, "_run_git", sneaky):
            with self.assertRaises(RuntimeError) as caught:
                self.apply()

        self.assertIn("unexpected new files", str(caught.exception))
        self.assertIn(b"return 1", self.read("sample.py"))


class ApplyApprovedPatchCrlfTests(ApplyApprovedPatchTests):
    line_ending = "\r\n"


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

        self.assertTrue(receipts.verify_signature(receipt))
        self.assertEqual(
            {k: v for k, v in receipt.items() if k != "signature"},
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


class DiffNormalizationTests(TemporaryRepoTestCase):
    """Common formatting differences are tidied when parsing."""

    GIT_HEADERS = (
        "diff --git a/sample.py b/sample.py\n"
        "index 1111111..2222222 100644\n"
    )

    def parse(self, diff, files=("sample.py",)):
        import json

        return proposal_module.parse_proposal(
            json.dumps(make_proposal(diff, files))
        )

    def test_valid_diff_is_unchanged(self):
        self.assertEqual(
            proposal_module._normalize_diff(GOOD_DIFF), GOOD_DIFF
        )

    def test_normalization_is_idempotent(self):
        messy = "\n" + self.GIT_HEADERS + GOOD_DIFF[:-2] + "\n\n"
        once = proposal_module._normalize_diff(messy)

        self.assertEqual(once, GOOD_DIFF)
        self.assertEqual(proposal_module._normalize_diff(once), once)

    def test_git_headers_removed(self):
        parsed = self.parse(self.GIT_HEADERS + GOOD_DIFF)
        self.assertEqual(parsed["diff"], GOOD_DIFF)

    def test_missing_final_newline_added(self):
        parsed = self.parse(GOOD_DIFF[:-1])
        self.assertEqual(parsed["diff"], GOOD_DIFF)

    def test_empty_context_line_repaired(self):
        # The final context line has lost its leading space.
        parsed = self.parse(GOOD_DIFF[:-2] + "\n")
        self.assertEqual(parsed["diff"], GOOD_DIFF)

    def test_surrounding_blank_lines_removed(self):
        parsed = self.parse("\n\n" + GOOD_DIFF + "\n\n")
        self.assertEqual(parsed["diff"], GOOD_DIFF)

    def test_two_files_with_git_headers(self):
        second = (
            "diff --git a/other.py b/other.py\n"
            "index 3333333..4444444 100644\n"
            "--- a/other.py\n"
            "+++ b/other.py\n"
            "@@ -1 +1 @@\n"
            "-y = 1\n"
            "+y = 2\n"
        )
        parsed = self.parse(
            self.GIT_HEADERS + GOOD_DIFF + second,
            ["sample.py", "other.py"],
        )

        self.assertNotIn("diff --git", parsed["diff"])
        self.assertNotIn("index ", parsed["diff"])

    def test_hunk_content_is_never_removed(self):
        diff = (
            "--- a/notes.txt\n"
            "+++ b/notes.txt\n"
            "@@ -1,4 +1,4 @@\n"
            " diff --git a/x b/x\n"
            "-index 1\n"
            "+index 2\n"
            "\n"
            " end\n"
        )
        expected = diff.replace("+index 2\n\n", "+index 2\n \n")

        self.assertEqual(proposal_module._normalize_diff(diff), expected)

    def test_parsed_diff_matches_fingerprinted_diff(self):
        parsed = self.parse(self.GIT_HEADERS + GOOD_DIFF[:-1])
        receipt = self.receipt(parsed)

        self.assertEqual(
            receipt["diff_hash"],
            patch_applier.calculate_diff_hash(GOOD_DIFF),
        )

        result = patch_applier.verify_patch_in_temporary_worktree(
            parsed, receipt
        )
        self.assertTrue(result["verified"])

    def test_forbidden_git_headers_still_rejected(self):
        forbidden = [
            "diff --git a/new.py b/new.py\nnew file mode 100644\n"
            "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x = 1\n",
            "diff --git a/other.py b/other.py\ndeleted file mode 100644\n"
            "--- a/other.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-y = 1\n",
            "diff --git a/other.py b/moved.py\nsimilarity index 100%\n"
            "rename from other.py\nrename to moved.py\n",
            "diff --git a/sample.py b/sample.py\nold mode 100644\n"
            "new mode 100755\n",
        ]

        for diff in forbidden:
            with self.subTest(diff=diff.splitlines()[1]):
                with self.assertRaises(ValueError):
                    self.parse(diff, ["sample.py"])

    def test_validator_itself_stays_strict(self):
        """Only parsing tidies; validation before applying does not."""
        for diff in (
            self.GIT_HEADERS + GOOD_DIFF,
            GOOD_DIFF[:-2] + "\n",
        ):
            with self.assertRaises(ValueError):
                proposal_module.validate_proposal(make_proposal(diff))

    def test_json_wrapped_in_markdown_and_prose(self):
        import json

        raw = (
            "Here is the proposal:\n```json\n"
            + json.dumps(make_proposal())
            + "\n```\nDone."
        )
        self.assertEqual(
            proposal_module.parse_proposal(raw)["diff"], GOOD_DIFF
        )

    def test_error_messages_identify_the_problem(self):
        cases = {
            "diff line 1 ('new file mode 100644')":
                "new file mode 100644\n" + GOOD_DIFF,
            "diff line 5 ('*   return 1')":
                GOOD_DIFF.replace("-    return 1", "*   return 1"),
            "must match the current file contents":
                GOOD_DIFF.replace("return 1", "return 9"),
        }

        for expected, diff in cases.items():
            with self.subTest(expected=expected):
                with self.assertRaises(ValueError) as caught:
                    self.parse(diff)

                self.assertIn(expected, str(caught.exception))

    def tearDown(self):
        self.assert_repo_untouched()


class ProposalRetryTests(TemporaryRepoTestCase):
    """generate_proposal retries with the rejection reason."""

    def run_with_responses(self, responses):
        import json

        prompts = []
        queue = [
            item if isinstance(item, str) else json.dumps(item)
            for item in responses
        ]

        def fake_claude(prompt):
            prompts.append(prompt)
            return queue.pop(0)

        with mock.patch.object(proposal_module, "ask_claude", fake_claude):
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    result = proposal_module.generate_proposal("Do it")
                except ValueError as error:
                    result = error

        return result, prompts

    def test_first_valid_answer_is_used(self):
        result, prompts = self.run_with_responses([make_proposal()])

        self.assertEqual(result["diff"], GOOD_DIFF)
        self.assertEqual(len(prompts), 1)

    def test_retry_includes_rejection_reason(self):
        bad = make_proposal(GOOD_DIFF.replace("return 1", "return 9"))
        result, prompts = self.run_with_responses(
            ["not json", bad, make_proposal()]
        )

        self.assertEqual(result["diff"], GOOD_DIFF)
        self.assertEqual(len(prompts), 3)
        self.assertIn("did not return valid JSON", prompts[1])
        self.assertIn("Git rejected the proposed patch", prompts[2])

    def test_gives_up_after_attempt_limit(self):
        limit = proposal_module.MAX_PROPOSAL_ATTEMPTS
        result, prompts = self.run_with_responses(["not json"] * (limit + 2))

        self.assertIsInstance(result, ValueError)
        self.assertEqual(len(prompts), limit)

    def test_empty_task_rejected_without_calling_claude(self):
        with mock.patch.object(
            proposal_module, "ask_claude", side_effect=AssertionError
        ):
            with self.assertRaises(ValueError):
                proposal_module.generate_proposal("   ")

    def tearDown(self):
        self.assert_repo_untouched()


if __name__ == "__main__":
    unittest.main()
