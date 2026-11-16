

from claude_agent import ask_claude
from openai_agent import ask_gpt


def main():
    print("=" * 60)
    print("TRASH ML - MULTI-AGENT SYSTEM")
    print("=" * 60)

    task = """
    Analyze the Trash ML project and identify its most important
    opportunities for improvement.

    Focus on model accuracy, webcam performance, and code quality.
    Do not modify any project files.
    """

    try:
        # STEP 1: GPT creates an investigation plan
        print("\n[1/3] GPT is preparing an investigation plan...\n")

        planning_prompt = f"""
        You are the planning agent for a Python machine learning project
        called Trash ML.

        Project context:
        - Uses TensorFlow and MobileNetV2.
        - Classifies glass, plastic, metal, and general_waste.
        - Has a webcam prediction feature.

        User task:
        {task}

        Create a concise investigation plan for Claude Code.
        Claude will have access to the actual project files.
        Tell Claude what to inspect and what evidence to collect.

        Do not pretend you have inspected the local files.
        Do not suggest modifying files during this test.
        """

        gpt_plan = ask_gpt(planning_prompt)

        print("GPT INVESTIGATION PLAN:")
        print("-" * 60)
        print(gpt_plan)

        # STEP 2: Claude inspects the actual project
        print("\n[2/3] Claude is inspecting the project...\n")

        claude_prompt = f"""
        You are the programming and code-analysis agent for Trash ML.

        User task:
        {task}

        Investigation plan from GPT:
        {gpt_plan}

        Inspect the actual project files and report your findings.

        Include:
        1. Important findings with relevant file names.
        2. Problems or risks you discovered.
        3. Recommended improvements, in priority order.
        4. Any uncertainties that need further investigation.

        IMPORTANT:
        Do not create, edit, delete, or modify any files.
        Only inspect and report.
        """

        claude_report = ask_claude(claude_prompt)

        print("CLAUDE REPORT:")
        print("-" * 60)
        print(claude_report)

        # STEP 3: GPT reviews Claude's findings
        print("\n[3/3] GPT is reviewing Claude's report...\n")

        review_prompt = f"""
        You are the independent reviewer for the Trash ML project.

        Review the following report produced by Claude Code.

        CLAUDE REPORT:
        {claude_report}

        Evaluate:
        1. Are the recommendations technically reasonable?
        2. Are there any unsupported claims?
        3. What risks should be considered?
        4. Which three improvements should be prioritized?

        Be critical and specific.

        Important:
        You cannot access the user's local files yourself.
        Do not claim to have independently verified Claude's findings.
        """

        gpt_review = ask_gpt(review_prompt)

        print("GPT FINAL REVIEW:")
        print("-" * 60)
        print(gpt_review)

        print("\n" + "=" * 60)
        print("MULTI-AGENT TEST COMPLETED SUCCESSFULLY!")
        print("=" * 60)

    except Exception as error:
        print("\nMULTI-AGENT SYSTEM ERROR:")
        print(error)


if __name__ == "__main__":
    main()