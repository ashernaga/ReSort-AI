
# Support both direct execution and package imports.
if __package__:
    from .openai_agent import ask_gpt
    from .proposal import generate_proposal
    from .approval import request_approval
    from .patch_applier import (
        apply_approved_patch,
        ensure_clean_working_tree,
    )
    from .checks import run_checks, format_checks
    from .reviewer import get_working_diff, review_change
else:
    from openai_agent import ask_gpt
    from proposal import generate_proposal
    from approval import request_approval
    from patch_applier import (
        apply_approved_patch,
        ensure_clean_working_tree,
    )
    from checks import run_checks, format_checks
    from reviewer import get_working_diff, review_change


def main():
    print("=" * 60)
    print("TRASH ML - HUMAN APPROVAL WORKFLOW")
    print("=" * 60)

    task = input("\nWhat change would you like to propose?\n> ").strip()

    if not task:
        print("No task provided. Exiting.")
        return

    try:
        # Fail early, before any API calls are made.
        try:
            ensure_clean_working_tree()
        except ValueError as error:
            print("\nCannot start: the project has uncommitted changes.")
            print("Commit them, or undo them, then run this again.\n")
            print(error)
            return

        # STEP 1: GPT creates an investigation plan.
        print("\n[1/6] GPT is preparing an investigation plan...\n")

        planning_prompt = f"""
You are the planning agent for the Trash ML Python project.

User task:
{task}

Create a concise investigation plan for Claude Code.
Tell Claude which files and functions to inspect.

Do not pretend you have inspected the local files.
Do not modify any files.
"""

        gpt_plan = ask_gpt(planning_prompt)

        print("\nGPT INVESTIGATION PLAN:")
        print("-" * 60)
        print(gpt_plan)

        # STEP 2: Claude generates a proposed change.
        print("\n[2/6] Claude is generating a proposal...\n")

        proposal = generate_proposal(
            task=task,
            investigation_plan=gpt_plan
        )

        print("\nClaude proposal generated and validated.")

        # STEP 3: User reviews and decides.
        print("\n[3/6] Waiting for human approval...\n")

        receipt = request_approval(proposal)

        if receipt is None or receipt.get("approved") is not True:
            print("\nPROPOSAL REJECTED.")
            print("No files have been modified.")
            return

        print("\nPROPOSAL APPROVED.")

        # STEP 4: Verify in a sandbox, then apply the exact approved diff.
        print("\n[4/6] Verifying and applying the approved patch...\n")

        result = apply_approved_patch(proposal, receipt)

        print("PATCH APPLIED.")
        print("Verified in a temporary worktree before applying.")
        print("Result matches the verified file contents.")
        print("Files changed (not staged, not committed):")

        for file_path in result["changed_files"]:
            print(f"  - {file_path}")

        # STEP 5: Automated checks. These report only.
        print("\n[5/6] Running checks...\n")

        checks = run_checks(result["changed_files"])
        checks_text = format_checks(checks)

        print(checks_text)

        # STEP 6: GPT reviews the applied change. It reports only.
        print("\n[6/6] GPT is reviewing the applied change...\n")

        try:
            applied_diff = get_working_diff(result["changed_files"])
            review = review_change(task, proposal, applied_diff, checks_text)

            print("GPT REVIEW:")
            print("-" * 60)
            print(review)
        except Exception as error:
            print(f"GPT review could not be completed: {error}")
            print("The change was still applied; review it yourself.")

        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETED")
        print("=" * 60)
        print("The change is in your working tree and is NOT committed.")
        print("Inspect it with:  git diff")
        print("To keep it, commit it yourself.")
        print("To undo it, run:")
        print(f"  {result['undo_command']}")

    except Exception as error:
        print("\nMULTI-AGENT SYSTEM ERROR:")
        print(error)


if __name__ == "__main__":
    main()
