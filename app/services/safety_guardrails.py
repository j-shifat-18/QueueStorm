"""
Safety Guardrails — post-process the LLM output to enforce fintech safety rules.

Rules enforced (per the problem statement Section 8):
  1. customer_reply must NEVER ask for PIN, OTP, password, or card number.
  2. customer_reply must NEVER confirm refund/reversal/unblock without authority.
  3. customer_reply must NEVER direct customer to suspicious third parties.
  4. Adversarial prompt-injection attempts are blocked.
"""

import re
from typing import Dict, Any

# ── Dangerous patterns that must NEVER appear in customer_reply ───────────────

CREDENTIAL_REQUEST_PATTERNS = [
    r"please share your (pin|otp|password|card)",
    r"\bshare your (pin|otp|password|card)\b",
    r"\b(send|provide|give|enter|type|tell us).{0,40}(pin|otp|password|card)\b",
    r"\bwhat is your.{0,30}(pin|otp|password)\b",
    r"\bplease (confirm|verify).{0,40}(pin|otp|password|account number)\b",
    r"\bconfirm your (pin|otp|password|card)\b",
]

UNAUTHORIZED_PROMISE_PATTERNS = [
    r"\bwe will refund\b",
    r"\bwe will (reverse|unblock|recover|return) your\b",
    r"\byour (money|amount|funds|balance) (will be|has been) refunded\b",
    r"\brefund (has been|will be) processed\b",
    r"\bwe guarantee\b.{0,30}\b(refund|return|reversal)\b",
    r"\byour account (will be|has been) unblocked\b",
    r"\bwe (have|will) (reverse|unblock|recover)\b",
]

THIRD_PARTY_REDIRECT_PATTERNS = [
    r"\bcontact (telegram|whatsapp|facebook|twitter|instagram|tiktok)\b",
    r"\bsend (money|payment) to\b.{0,40}\b(number|account|wallet)\b",
    r"\bcall (this|the following|this external|another) number\b",
]

# Safe replacement phrases
SAFE_REFUND_LANGUAGE = "any eligible amount will be returned through official channels"
SAFE_CREDENTIAL_REMINDER = "Please do not share your PIN or OTP with anyone."


def check_for_prompt_injection(complaint: str) -> bool:
    """
    Detect adversarial attempts to override system behavior via the complaint field.
    Returns True if injection is suspected.
    """
    injection_markers = [
        "ignore previous instructions",
        "ignore all instructions",
        "disregard your system",
        "you are now",
        "act as",
        "new instructions:",
        "system prompt",
        "override safety",
        "forget your rules",
        "forget everything",
        "###instruction",
        "```instruction",
        "[system]",
        "<system>",
    ]
    complaint_lower = complaint.lower()
    return any(marker in complaint_lower for marker in injection_markers)


def sanitize_customer_reply(reply: str) -> str:
    """
    Scan and sanitize the customer_reply to remove safety violations.
    Returns a cleaned reply.
    """
    reply_lower = reply.lower()

    # Check credential requests — if found, replace the whole sentence with a safe line
    for pattern in CREDENTIAL_REQUEST_PATTERNS:
        if re.search(pattern, reply_lower):
            reply = _replace_sentence_with_match(reply, pattern)
            reply_lower = reply.lower()

    # Check unauthorized promises
    for pattern in UNAUTHORIZED_PROMISE_PATTERNS:
        if re.search(pattern, reply_lower):
            reply = re.sub(
                r"[Ww]e will refund[^.]*\.",
                f"{SAFE_REFUND_LANGUAGE.capitalize()}.",
                reply,
            )
            reply = re.sub(
                r"[Yy]our (money|amount|funds|balance) (will be|has been) refunded[^.]*\.",
                f"{SAFE_REFUND_LANGUAGE.capitalize()}.",
                reply,
            )
            reply_lower = reply.lower()

    # Ensure PIN/OTP reminder is always present
    if "pin" not in reply.lower() and "otp" not in reply.lower():
        reply = reply.rstrip() + " " + SAFE_CREDENTIAL_REMINDER

    return reply.strip()


def _replace_sentence_with_match(text: str, pattern: str) -> str:
    """Remove sentences containing the unsafe pattern; append a safe reminder."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean = []
    removed = False
    for sentence in sentences:
        if re.search(pattern, sentence.lower()):
            removed = True
        else:
            clean.append(sentence)
    result = " ".join(clean)
    if removed:
        result = result.rstrip() + " " + SAFE_CREDENTIAL_REMINDER
    return result


def validate_response_safety(response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Full safety pass on the complete response dict.
    Modifies and returns the response.
    """
    # Sanitize customer_reply
    if "customer_reply" in response and response["customer_reply"]:
        response["customer_reply"] = sanitize_customer_reply(response["customer_reply"])

    # Ensure recommended_next_action never promises unauthorized financial actions
    if "recommended_next_action" in response and response["recommended_next_action"]:
        action = response["recommended_next_action"]
        for pattern in UNAUTHORIZED_PROMISE_PATTERNS:
            if re.search(pattern, action.lower()):
                response["recommended_next_action"] = action.replace(
                    "refund", "review for potential refund eligibility"
                ).replace("reverse", "review for potential reversal")

    # Force human_review_required=True for critical severity or phishing
    severity = response.get("severity", "")
    case_type = response.get("case_type", "")
    if severity == "critical" or case_type == "phishing_or_social_engineering":
        response["human_review_required"] = True

    # Clamp confidence to [0, 1]
    if "confidence" in response and response["confidence"] is not None:
        response["confidence"] = max(0.0, min(1.0, float(response["confidence"])))

    return response


def get_fallback_response(ticket_id: str, complaint: str, is_injection: bool = False) -> Dict[str, Any]:
    """
    Return a safe fallback response when the LLM fails or injection is detected.
    """
    return {
        "ticket_id": ticket_id,
        "relevant_transaction_id": None,
        "evidence_verdict": "insufficient_data",
        "case_type": "other",
        "severity": "low",
        "department": "customer_support",
        "agent_summary": "Unable to automatically process this ticket. Manual review required.",
        "recommended_next_action": "Route to a human support agent for manual review.",
        "customer_reply": (
            "Thank you for reaching out. We have received your message and our support team "
            "will review it shortly. Please do not share your PIN or OTP with anyone."
        ),
        "human_review_required": True,
        "confidence": 0.0,
        "reason_codes": ["fallback", "injection_detected" if is_injection else "processing_error"],
    }
