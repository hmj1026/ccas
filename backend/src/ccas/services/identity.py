"""Reconciliation identity calculation and sensitive data checks.

Implements canonical percent-encoding and stable reconciliation keys for
Bill and Transaction entities per specs/reconciliation-identity/spec.md.
"""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Sequence
from datetime import date

from ccas.services.schemas import AgentQueryError

# Matches full PAN (13 to 19 digits, possibly with separators like spaces or hyphens)
PAN_REGEX = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")

# Matches credential-labeled tokens/passwords/secrets
CREDENTIAL_REGEX = re.compile(
    r"(?i)\b(?:password|passwd|token|session_secret|secret|bearer)\s*[:=]\s*\S+"
)


CARD_LAST4_REGEX = re.compile(r"^[0-9]{4}$")


def contains_sensitive_data(text: str | None) -> bool:
    """Check if text contains credential tokens or full PANs."""
    if not text:
        return False

    # Check for credentials
    if CREDENTIAL_REGEX.search(text):
        return True

    # Check for full PAN
    for match in PAN_REGEX.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19:
            return True

    return False


def sanitize_text(text: str | None) -> str:
    """Mask credentials and full PANs across text fields."""
    if not text:
        return ""

    # Redact credential patterns
    sanitized = CREDENTIAL_REGEX.sub("[REDACTED_CREDENTIAL]", text)

    # Redact PAN patterns
    def _mask_pan(match: re.Match[str]) -> str:
        s = match.group(0)
        digits = re.sub(r"\D", "", s)
        if 13 <= len(digits) <= 19:
            return "[REDACTED_PAN]"
        return s

    return PAN_REGEX.sub(_mask_pan, sanitized)


def canonical_quote(value: str) -> str:
    """Canonical percent-encoding preserving only [A-Za-z0-9._~-].

    All other bytes are encoded as uppercase %HH.
    """
    return urllib.parse.quote(str(value), safe="-._~")


def build_bill_reconciliation_key(
    bank_code: str,
    billing_month: str,
    card_last4s: Sequence[str],
    due_date: date,
) -> str:
    """Derive Bill reconciliation key.

    Helper itself sorts and deduplicates nonempty ASCII four-digit cards.
    Format:
    - With cards: {bank_code}:{billing_month}:{sorted_last4s}
    - No cards:   {bank_code}:{billing_month}:due-{due_date.isoformat()}
    """
    if contains_sensitive_data(bank_code) or contains_sensitive_data(billing_month):
        raise AgentQueryError(
            "needs_human",
            "Bill data contains sensitive information requiring human review.",
            needs_human=True,
        )

    encoded_bank = canonical_quote(bank_code)
    encoded_month = canonical_quote(billing_month)

    clean_cards: list[str] = sorted(
        {c for c in card_last4s if c and CARD_LAST4_REGEX.match(c)}
    )
    if clean_cards:
        cards_str = ",".join(canonical_quote(c) for c in clean_cards)
        return f"{encoded_bank}:{encoded_month}:{cards_str}"

    fallback = canonical_quote(f"due-{due_date.isoformat()}")
    return f"{encoded_bank}:{encoded_month}:{fallback}"


def build_transaction_reconciliation_key(
    bill_id: int,
    trans_date: date,
    amount: int,
    merchant: str,
    dup_ordinal: int = 1,
) -> str:
    """Derive Transaction reconciliation key.

    Format:
    - Base: {bill_id}:{trans_date}:{amount}:{merchant}
    - Duplicate: {base}#{dup_ordinal} for dup_ordinal >= 2
    """
    if contains_sensitive_data(merchant):
        raise AgentQueryError(
            "needs_human",
            "Transaction merchant contains sensitive information.",
            needs_human=True,
        )

    encoded_bill_id = canonical_quote(str(bill_id))
    encoded_date = canonical_quote(trans_date.isoformat())
    encoded_amount = canonical_quote(str(amount))
    encoded_merchant = canonical_quote(merchant)

    base_key = f"{encoded_bill_id}:{encoded_date}:{encoded_amount}:{encoded_merchant}"
    if dup_ordinal > 1:
        return f"{base_key}#{dup_ordinal}"
    return base_key
