
from openai_agent import ask_gpt
from proposal import generate_proposal
from approval import request_approval


def main():
    print("=" * 60)
    print("TRASH ML - HUMAN APPROVAL WORKFLOW")
    print("=" * 60)

    task = input("\nWhat change would you like to propose?\n> ").strip()

    if not task:
        print("No task provided. Exiting.")
        return

    try:
        # STEP 1: GPT creates an investigation plan
        print("\n[1/3] GPT is preparing an investigation plan...\n")

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

        # STEP 2: Claude generates a proposed change
        print("\n[2/3] Claude is generating a proposal...\n")

        proposal = generate_proposal(
            task=task,
            investigation_plan=gpt_plan
        )

        print("\nClaude proposal generated and validated.")

        # STEP 3: User reviews and decides
        print("\n[3/3] Waiting for human approval...\n")

        approved = request_approval(proposal)

        if approved:
            print("\nPROPOSAL AUTHORIZED.")
            print("No files have been modified.")
            print("Patch application is not implemented yet.")
        else:
            print("\nPROPOSAL REJECTED.")
            print("No files have been modified.")

        print("\n" + "=" * 60)
        print("WORKFLOW COMPLETED")
        print("=" * 60)

    except Exception as error:
        print("\nMULTI-AGENT SYSTEM ERROR:")
        print(error)


if __name__ == "__main__":
    main()
