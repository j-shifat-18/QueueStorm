"""
Main analyzer orchestrator.

Pipeline:
  1. Check for prompt injection in complaint
  2. Run rule-based evidence engine (transaction matching, case classification)
  3. Call Gemini with pre-computed evidence injected into prompt
  4. Validate and sanitize response with safety guardrails
  5. Merge rule-based overrides where LLM output is unsafe/invalid
  6. Persist to database
  7. Return final TicketResponse
"""

import logging
import time
from typing import Optional, List, Dict, Any

from app.models.schemas import TicketRequest, TicketResponse
from app.services.evidence_engine import find_relevant_transaction, classify_case_type
from app.services.safety_guardrails import (
    check_for_prompt_injection,
    validate_response_safety,
    get_fallback_response,
)
from app.services.gemini_service import analyze_ticket_with_gemini

logger = logging.getLogger(__name__)

# Valid enum sets
VALID_EVIDENCE_VERDICTS = {"consistent", "inconsistent", "insufficient_data"}
VALID_CASE_TYPES = {
    "wrong_transfer", "payment_failed", "refund_request", "duplicate_payment",
    "merchant_settlement_delay", "agent_cash_in_issue",
    "phishing_or_social_engineering", "other",
}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_DEPARTMENTS = {
    "customer_support", "dispute_resolution", "payments_ops",
    "merchant_operations", "agent_operations", "fraud_risk",
}


def _coerce_enums(response: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all enum fields are valid; fall back to safe defaults."""
    if response.get("evidence_verdict") not in VALID_EVIDENCE_VERDICTS:
        response["evidence_verdict"] = "insufficient_data"
    if response.get("case_type") not in VALID_CASE_TYPES:
        response["case_type"] = "other"
    if response.get("severity") not in VALID_SEVERITIES:
        response["severity"] = "medium"
    if response.get("department") not in VALID_DEPARTMENTS:
        response["department"] = "customer_support"
    return response


def _department_for_case_type(case_type: str, severity: str) -> str:
    mapping = {
        "wrong_transfer": "dispute_resolution",
        "payment_failed": "payments_ops",
        "duplicate_payment": "payments_ops",
        "refund_request": "dispute_resolution" if severity in ("high", "critical") else "customer_support",
        "merchant_settlement_delay": "merchant_operations",
        "agent_cash_in_issue": "agent_operations",
        "phishing_or_social_engineering": "fraud_risk",
        "other": "customer_support",
    }
    return mapping.get(case_type, "customer_support")


def _should_require_human_review(case_type: str, severity: str, verdict: str) -> bool:
    if case_type in ("wrong_transfer", "duplicate_payment", "phishing_or_social_engineering"):
        return True
    if severity in ("high", "critical"):
        return True
    if verdict == "inconsistent":
        return True
    return False


async def analyze_ticket(request: TicketRequest, db=None) -> TicketResponse:
    start_time = time.time()
    complaint = request.complaint.strip()
    ticket_id = request.ticket_id
    transactions = [t.dict() for t in (request.transaction_history or [])]
    user_type = request.user_type or "customer"
    language = request.language or "en"

    # ── Step 1: Prompt injection check ────────────────────────────────────────
    if check_for_prompt_injection(complaint):
        logger.warning(f"Prompt injection detected in ticket {ticket_id}")
        fallback = get_fallback_response(ticket_id, complaint, is_injection=True)
        return TicketResponse(**fallback)

    # ── Step 2: Rule-based evidence engine ───────────────────────────────────
    suggested_txn_id, suggested_verdict, rule_reason_codes = find_relevant_transaction(
        complaint, transactions
    )
    suggested_case_type = classify_case_type(complaint.lower(), transactions, user_type)

    # ── Step 3: Gemini analysis ───────────────────────────────────────────────
    llm_response = await analyze_ticket_with_gemini(
        ticket_id=ticket_id,
        complaint=complaint,
        language=language,
        channel=request.channel,
        user_type=user_type,
        campaign_context=request.campaign_context,
        transactions=transactions,
        suggested_txn_id=suggested_txn_id,
        suggested_verdict=suggested_verdict,
        suggested_case_type=suggested_case_type,
        reason_codes=rule_reason_codes,
    )

    # ── Step 4: Fallback if LLM fails ────────────────────────────────────────
    if not llm_response:
        logger.warning(f"LLM failed for ticket {ticket_id}, using rule-based fallback")
        llm_response = _build_rule_based_response(
            ticket_id=ticket_id,
            complaint=complaint,
            language=language,
            user_type=user_type,
            transactions=transactions,
            suggested_txn_id=suggested_txn_id,
            suggested_verdict=suggested_verdict,
            suggested_case_type=suggested_case_type,
            rule_reason_codes=rule_reason_codes,
        )

    # ── Step 5: Enforce ticket_id echo ───────────────────────────────────────
    llm_response["ticket_id"] = ticket_id

    # ── Step 6: Coerce enums ─────────────────────────────────────────────────
    llm_response = _coerce_enums(llm_response)

    # ── Step 7: Rule overrides ────────────────────────────────────────────────
    # If rule engine found a specific transaction, trust it over LLM
    if suggested_txn_id and not llm_response.get("relevant_transaction_id"):
        llm_response["relevant_transaction_id"] = suggested_txn_id

    # Fix department based on case_type if mismatched
    case_type = llm_response.get("case_type", "other")
    severity = llm_response.get("severity", "medium")
    correct_dept = _department_for_case_type(case_type, severity)
    # Only override if LLM returned wrong department for critical cases
    if case_type == "phishing_or_social_engineering":
        llm_response["department"] = "fraud_risk"
        llm_response["severity"] = "critical"

    # Compute human_review_required
    verdict = llm_response.get("evidence_verdict", "insufficient_data")
    llm_response["human_review_required"] = _should_require_human_review(
        case_type, severity, verdict
    )

    # ── Step 8: Safety pass ──────────────────────────────────────────────────
    llm_response = validate_response_safety(llm_response)

    # ── Step 9: Persist to DB ────────────────────────────────────────────────
    processing_ms = (time.time() - start_time) * 1000
    if db is not None:
        await _persist_ticket(db, request, llm_response, processing_ms)

    logger.info(
        f"Ticket {ticket_id} analyzed in {processing_ms:.0f}ms | "
        f"case_type={llm_response.get('case_type')} | "
        f"verdict={llm_response.get('evidence_verdict')} | "
        f"severity={llm_response.get('severity')}"
    )

    return TicketResponse(**llm_response)


def _build_rule_based_response(
    ticket_id: str,
    complaint: str,
    language: str,
    user_type: str,
    transactions: List[Dict],
    suggested_txn_id: Optional[str],
    suggested_verdict: str,
    suggested_case_type: str,
    rule_reason_codes: List[str],
) -> Dict[str, Any]:
    """Pure rule-based fallback when Gemini is unavailable."""
    severity_map = {
        "phishing_or_social_engineering": "critical",
        "wrong_transfer": "high",
        "duplicate_payment": "high",
        "payment_failed": "high",
        "agent_cash_in_issue": "high",
        "merchant_settlement_delay": "medium",
        "refund_request": "low",
        "other": "low",
    }
    dept = _department_for_case_type(suggested_case_type, severity_map.get(suggested_case_type, "medium"))
    severity = severity_map.get(suggested_case_type, "medium")

    txn_ref = f" regarding transaction {suggested_txn_id}" if suggested_txn_id else ""

    # Bangla fallback reply
    if language == "bn":
        customer_reply = (
            f"আপনার অভিযোগ{txn_ref} আমরা পেয়েছি। আমাদের সাপোর্ট টিম শীঘ্রই এটি পর্যালোচনা করবে। "
            "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
        )
    else:
        customer_reply = (
            f"Thank you for reaching out. We have received your concern{txn_ref}. "
            "Our support team will review it and contact you through official channels. "
            "Please do not share your PIN or OTP with anyone."
        )

    return {
        "ticket_id": ticket_id,
        "relevant_transaction_id": suggested_txn_id,
        "evidence_verdict": suggested_verdict,
        "case_type": suggested_case_type,
        "severity": severity,
        "department": dept,
        "agent_summary": f"Ticket classified as {suggested_case_type.replace('_', ' ')} based on complaint text and transaction history.",
        "recommended_next_action": f"Route to {dept.replace('_', ' ')} for review. Human agent should verify the case details.",
        "customer_reply": customer_reply,
        "human_review_required": True,
        "confidence": 0.6,
        "reason_codes": rule_reason_codes + ["rule_based_fallback"],
    }


async def _persist_ticket(db, request: TicketRequest, response: Dict, processing_ms: float):
    """Persist the ticket and analysis to the database."""
    try:
        from app.db.models import TicketLog
        log = TicketLog(
            ticket_id=request.ticket_id,
            complaint=request.complaint,
            language=request.language,
            channel=request.channel,
            user_type=request.user_type,
            campaign_context=request.campaign_context,
            transaction_history=[t.dict() for t in (request.transaction_history or [])],
            relevant_transaction_id=response.get("relevant_transaction_id"),
            evidence_verdict=response.get("evidence_verdict"),
            case_type=response.get("case_type"),
            severity=response.get("severity"),
            department=response.get("department"),
            agent_summary=response.get("agent_summary"),
            recommended_next_action=response.get("recommended_next_action"),
            customer_reply=response.get("customer_reply"),
            human_review_required=response.get("human_review_required"),
            confidence=response.get("confidence"),
            reason_codes=response.get("reason_codes"),
            processing_time_ms=processing_ms,
        )
        db.add(log)
        await db.commit()
    except Exception as e:
        logger.error(f"Failed to persist ticket {request.ticket_id}: {e}")
        await db.rollback()
