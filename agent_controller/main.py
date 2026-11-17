
# Support both direct execution and package imports.
if __package__:
    from .openai_agent import ask_gpt
    from .proposal import generate_proposal
    from .approval import request_approval
    from .patch_applier import validate_patch_application
else:
    from openai_agent import ask_gpt
    from proposal import generate_proposal
    from approval import request_approval
    from patch_applier import validate_patch_application


def main():
    print("=" * 60)
    print("TRASH ML - HUMAN APPROVAL WORKFLOW")
    print("=" * 60)

    task = input("\nWhat change would you like to propose?\n> ").strip()

    if not task:
        print("No task provided. Exiting.")
        return

    try:
        # STEP 1: GPT creates an investigation plan.
        print("\n[1/4] GPT is preparing an investigation plan...\n")

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
        print("\n[2/4] Claude is generating a proposal...\n")

        proposal = generate_proposal(
            task=task,
            investigation_plan=gpt_plan
        )

        print("\nClaude proposal generated and validated.")

        # STEP 3: User reviews and decides.
        print("\n[3/4] Waiting for human approval...\n")

        receipt = request_approval(proposal)

        if receipt is None or receipt.get("approved") is not True:
            print("\nPROPOSAL REJECTED.")
            print("No files have been modified.")
            return

        print("\nPROPOSAL APPROVED.")
        print("Approval receipt received.")

        # STEP 4: Validate the exact approved patch.
        print("\n[4/4] Performing final dry-run validation...\n")

        validate_patch_application(proposal, receipt)

        print("\nDRY-RUN VALIDATION PASSED.")
        print("Approval receipt verified.")
        print("Git baseline verified.")
        print("Patch structure and file paths verified.")
        print("Git accepted the patch check.")
        print("\nNo files have been modified.")

        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETED")
        print("=" * 60)

    except Exception as error:
        print("\nMULTI-AGENT SYSTEM ERROR:")
        print(error)


if __name__ == "__main__":
    main()
