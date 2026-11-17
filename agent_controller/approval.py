
# Support both direct execution and package imports
if __package__:
    from .proposal import validate_proposal
    from .receipts import sign_receipt
    from .patch_applier import (
        get_current_commit,
        ensure_clean_working_tree,
        calculate_diff_hash,
    )
else:
    from proposal import validate_proposal
    from receipts import sign_receipt
    from patch_applier import (
        get_current_commit,
        ensure_clean_working_tree,
        calculate_diff_hash,
    )


def request_approval(proposal: dict) -> dict | None:
    """
    Display a proposed change and request explicit approval.

    Returns an approval receipt containing the exact diff hash
    and original Git baseline, or None if rejected.

    This function does not apply any changes.
    """

    if not isinstance(proposal, dict):
        print("REJECTED: Invalid proposal format.")
        return None

    try:
        # Establish a clean Git baseline before displaying the proposal.
        ensure_clean_working_tree()
        baseline_commit = get_current_commit()

        # Validate the proposal, including paths and exact diff.
        validate_proposal(proposal)

        # Ensure the repository has not changed during validation.
        if get_current_commit() != baseline_commit:
            raise RuntimeError(
                "Git baseline changed during proposal validation."
            )

        ensure_clean_working_tree()

    except (ValueError, RuntimeError) as error:
        print(f"REJECTED: Proposal validation failed: {error}")
        print("\nNo changes authorized.")
        return None

    print("\n" + "=" * 60)
    print("HUMAN APPROVAL REQUIRED")
    print("=" * 60)

    print("\nPROPOSED CHANGE:")
    print(proposal["summary"])

    print("\nFILES AFFECTED:")

    for file_path in proposal["files"]:
        print(f"  - {file_path}")

    print("\nCHANGE DETAILS:")
    print(proposal["details"])

    print("\nEXACT PROPOSED DIFF:")
    print("=" * 60)
    print(proposal["diff"])
    print("=" * 60)

    # Fingerprint the exact diff shown to the user.
    diff_hash = calculate_diff_hash(proposal["diff"])

    print("\n" + "-" * 60)
    print("Type APPROVE to accept this proposal.")
    print(
        "Approving will MODIFY the files listed above in your working "
        "tree. The change is not committed."
    )
    print("Anything else will reject it.")

    decision = input("\nYour decision: ").strip()

    if decision != "APPROVE":
        print("\nProposal rejected. No changes authorized.")
        return None

    try:
        # Recheck that the original Git baseline is unchanged.
        if get_current_commit() != baseline_commit:
            raise RuntimeError(
                "Git baseline changed while approval was pending."
            )

        # Reject any tracked or untracked changes made during approval.
        ensure_clean_working_tree()

    except (ValueError, RuntimeError) as error:
        print(f"\nREJECTED: Approval verification failed: {error}")
        print("A new proposal and approval are required.")
        return None

    receipt = sign_receipt(
        {
            "approved": True,
            "diff_hash": diff_hash,
            "baseline_commit": baseline_commit,
        }
    )

    print("\nProposal approved by the user.")
    print("Approval receipt created.")

    return receipt
