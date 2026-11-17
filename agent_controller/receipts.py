"""
Signed, single-use approval receipts.

A receipt is created only by the approval step, after the user types
APPROVE. It is signed with a random key that exists only in the memory
of the running program, so a receipt written by hand, copied from an
earlier run, or edited after approval does not verify.

This protects against mistakes and stale or forged receipts. It does
not defend against malicious code running inside this same Python
process, which could read the key.
"""

import hashlib
import hmac
import json
import secrets

# Created fresh every time the program starts; never written to disk.
_SESSION_KEY = secrets.token_bytes(32)

# Signatures of receipts that have already been used to apply a patch.
_consumed_signatures = set()

_SIGNED_FIELDS = ("approved", "diff_hash", "baseline_commit")


def _signature_for(receipt: dict) -> str:
    payload = json.dumps(
        {field: receipt.get(field) for field in _SIGNED_FIELDS},
        sort_keys=True,
        separators=(",", ":"),
        default=repr,
    ).encode("utf-8")

    return hmac.new(_SESSION_KEY, payload, hashlib.sha256).hexdigest()


def sign_receipt(receipt: dict) -> dict:
    """Return a copy of the receipt carrying a valid signature."""

    signed = {
        key: value for key, value in receipt.items() if key != "signature"
    }
    signed["signature"] = _signature_for(signed)

    return signed


def verify_signature(receipt: dict) -> bool:
    """Return True only if the receipt was signed by this program run."""

    if not isinstance(receipt, dict):
        return False

    signature = receipt.get("signature")

    if not isinstance(signature, str):
        return False

    return hmac.compare_digest(signature, _signature_for(receipt))


def consume_receipt(receipt: dict) -> None:
    """Mark a receipt as used. A receipt can authorize one application."""

    if not verify_signature(receipt):
        raise ValueError(
            "Approval receipt was not signed by this approval session."
        )

    signature = receipt["signature"]

    if signature in _consumed_signatures:
        raise ValueError(
            "This approval receipt has already been used. "
            "A new approval is required."
        )

    _consumed_signatures.add(signature)
