"""
Evidence Engine — rule-based transaction matching and verdict logic.

This module runs BEFORE the LLM call so we can inject structured evidence
into the prompt, improving accuracy and reducing hallucination.
"""

from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timezone


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def find_relevant_transaction(
    complaint: str,
    transactions: List[Dict[str, Any]],
) -> Tuple[Optional[str], str, List[str]]:
    """
    Returns (relevant_transaction_id, evidence_verdict, reason_codes).

    Logic:
    1. No transactions → insufficient_data
    2. Try to match by amount mentioned in complaint + transaction type hints
    3. Detect duplicate patterns (same amount, same counterparty, within 60s)
    4. Detect inconsistency (e.g., repeat transfers to same recipient)
    5. Multiple ambiguous matches → insufficient_data
    """
    if not transactions:
        return None, "insufficient_data", ["no_transaction_history"]

    complaint_lower = complaint.lower()

    # ── Extract amounts mentioned in complaint ─────────────────────────────────
    import re
    amounts_in_complaint = []
    # Match patterns like "5000 taka", "5,000", "৳5000", "BDT 5000", "2000"
    for m in re.finditer(r"(?:bdt|taka|tk|৳)?\s*(\d[\d,]*)\s*(?:taka|tk|bdt)?", complaint_lower):
        try:
            val = float(m.group(1).replace(",", ""))
            if val > 0:
                amounts_in_complaint.append(val)
        except ValueError:
            pass

    # ── Detect duplicate payment ───────────────────────────────────────────────
    duplicate_id = _detect_duplicate(transactions)
    if duplicate_id:
        return duplicate_id, "consistent", ["duplicate_payment", "near_identical_transactions"]

    # ── Filter by mentioned amount ─────────────────────────────────────────────
    matched_by_amount: List[Dict] = []
    if amounts_in_complaint:
        for txn in transactions:
            if txn.get("amount") in amounts_in_complaint:
                matched_by_amount.append(txn)
    else:
        matched_by_amount = list(transactions)

    # ── Keyword-type hints ─────────────────────────────────────────────────────
    type_hints = _infer_type_hints(complaint_lower)
    if type_hints and matched_by_amount:
        type_filtered = [t for t in matched_by_amount if t.get("type") in type_hints]
        if type_filtered:
            matched_by_amount = type_filtered

    # ── Status hints ──────────────────────────────────────────────────────────
    # If complaint mentions "failed", "deducted", prefer failed/pending txns
    if any(w in complaint_lower for w in ["failed", "not received", "not reflected", "deducted"]):
        status_filtered = [t for t in matched_by_amount if t.get("status") in ("failed", "pending")]
        if status_filtered:
            matched_by_amount = status_filtered

    # ── Single match → pick it ────────────────────────────────────────────────
    if len(matched_by_amount) == 1:
        txn = matched_by_amount[0]
        verdict, codes = _compute_verdict(complaint_lower, txn, transactions)
        return txn["transaction_id"], verdict, codes

    # ── Multiple matches → ambiguous ──────────────────────────────────────────
    if len(matched_by_amount) > 1:
        # Try to pick most recent
        dated = [(t, _parse_iso(t.get("timestamp", ""))) for t in matched_by_amount]
        dated = [(t, d) for t, d in dated if d is not None]
        if dated:
            dated.sort(key=lambda x: x[1], reverse=True)
            # If all same type/amount/counterparty, still ambiguous
            counterparties = {t.get("counterparty") for t, _ in dated}
            if len(counterparties) > 1:
                return None, "insufficient_data", ["ambiguous_match", "needs_clarification"]
            # Same counterparty multiple matches — pick most recent
            txn = dated[0][0]
            verdict, codes = _compute_verdict(complaint_lower, txn, transactions)
            return txn["transaction_id"], verdict, codes
        return None, "insufficient_data", ["ambiguous_match"]

    # ── No amount match at all ────────────────────────────────────────────────
    # If only one transaction overall, use it tentatively
    if len(transactions) == 1:
        txn = transactions[0]
        verdict, codes = _compute_verdict(complaint_lower, txn, transactions)
        return txn["transaction_id"], verdict, codes

    return None, "insufficient_data", ["no_amount_match"]


def _detect_duplicate(transactions: List[Dict]) -> Optional[str]:
    """Return the transaction_id of the likely duplicate (second occurrence)."""
    for i, t1 in enumerate(transactions):
        for j, t2 in enumerate(transactions):
            if i >= j:
                continue
            same_amount = t1.get("amount") == t2.get("amount")
            same_counterparty = t1.get("counterparty") == t2.get("counterparty")
            same_type = t1.get("type") == t2.get("type")
            both_completed = (
                t1.get("status") == "completed" and t2.get("status") == "completed"
            )
            if same_amount and same_counterparty and same_type and both_completed:
                d1 = _parse_iso(t1.get("timestamp", ""))
                d2 = _parse_iso(t2.get("timestamp", ""))
                if d1 and d2:
                    diff = abs((d1 - d2).total_seconds())
                    if diff <= 120:  # within 2 minutes
                        # Return the later one as the duplicate
                        later = t2 if d2 > d1 else t1
                        return later["transaction_id"]
    return None


def _infer_type_hints(complaint_lower: str) -> List[str]:
    hints = []
    if any(w in complaint_lower for w in ["transfer", "sent", "send", "wrong number", "wrong person"]):
        hints.append("transfer")
    if any(w in complaint_lower for w in ["payment", "paid", "pay", "bill", "recharge", "merchant"]):
        hints.append("payment")
    if any(w in complaint_lower for w in ["cash in", "cash-in", "cashin", "deposit", "agent"]):
        hints.append("cash_in")
    if any(w in complaint_lower for w in ["cash out", "cash-out", "cashout", "withdraw"]):
        hints.append("cash_out")
    if any(w in complaint_lower for w in ["settlement", "settle"]):
        hints.append("settlement")
    if any(w in complaint_lower for w in ["refund", "money back", "return"]):
        hints.append("refund")
    return hints


def _compute_verdict(
    complaint_lower: str,
    txn: Dict,
    all_transactions: List[Dict],
) -> Tuple[str, List[str]]:
    """Compute evidence_verdict for a chosen transaction."""
    reason_codes = []

    # Check if same recipient appears multiple times (inconsistency for wrong_transfer)
    counterparty = txn.get("counterparty", "")
    same_recipient_count = sum(
        1 for t in all_transactions if t.get("counterparty") == counterparty
    )
    if same_recipient_count > 1 and any(
        w in complaint_lower for w in ["wrong", "mistake", "accidentally"]
    ):
        reason_codes.append("established_recipient_pattern")
        reason_codes.append("evidence_inconsistent")
        return "inconsistent", reason_codes

    # Amount match
    reason_codes.append("transaction_match")
    return "consistent", reason_codes


def classify_case_type(complaint_lower: str, transactions: List[Dict], user_type: str) -> str:
    """Rule-based case type classification as pre-hint for the LLM."""
    # Phishing / social engineering (highest priority)
    if any(w in complaint_lower for w in [
        "otp", "pin", "password", "scam", "fraud", "phishing",
        "someone called", "called me", "fake", "hacker", "account block",
        "share your", "asked for", "impersonat",
    ]):
        return "phishing_or_social_engineering"

    # Duplicate payment
    if _detect_duplicate(transactions):
        return "duplicate_payment"

    # Merchant settlement
    if user_type == "merchant" and any(w in complaint_lower for w in [
        "settlement", "settle", "not received", "pending"
    ]):
        return "merchant_settlement_delay"

    # Agent cash-in
    if any(w in complaint_lower for w in ["cash in", "cash-in", "cashin", "agent", "এজেন্ট", "ক্যাশ ইন"]):
        return "agent_cash_in_issue"

    # Payment failed
    if any(w in complaint_lower for w in [
        "failed", "payment failed", "not received", "deducted", "balance"
    ]):
        if any(t.get("type") == "payment" for t in transactions):
            return "payment_failed"

    # Wrong transfer
    if any(w in complaint_lower for w in [
        "wrong", "mistake", "wrong number", "wrong person", "sent to", "sent",
        "পাঠিয়েছি", "ভুল", "wrong transfer"
    ]):
        return "wrong_transfer"

    # Refund request
    if any(w in complaint_lower for w in ["refund", "money back", "return", "reimburse"]):
        return "refund_request"

    # Payment failed (generic)
    if any(t.get("status") in ("failed", "pending") for t in transactions):
        return "payment_failed"

    return "other"
