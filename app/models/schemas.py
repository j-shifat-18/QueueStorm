from typing import Optional, List, Any
from pydantic import BaseModel, Field, field_validator, model_validator


# ─── Enums (as string literals for strict validation) ─────────────────────────

LANGUAGE_ENUM = {"en", "bn", "mixed"}
CHANNEL_ENUM = {"in_app_chat", "call_center", "email", "merchant_portal", "field_agent"}
USER_TYPE_ENUM = {"customer", "merchant", "agent", "unknown"}
TRANSACTION_TYPE_ENUM = {"transfer", "payment", "cash_in", "cash_out", "settlement", "refund"}
TRANSACTION_STATUS_ENUM = {"completed", "failed", "pending", "reversed"}

EVIDENCE_VERDICT_ENUM = {"consistent", "inconsistent", "insufficient_data"}
CASE_TYPE_ENUM = {
    "wrong_transfer",
    "payment_failed",
    "refund_request",
    "duplicate_payment",
    "merchant_settlement_delay",
    "agent_cash_in_issue",
    "phishing_or_social_engineering",
    "other",
}
SEVERITY_ENUM = {"low", "medium", "high", "critical"}
DEPARTMENT_ENUM = {
    "customer_support",
    "dispute_resolution",
    "payments_ops",
    "merchant_operations",
    "agent_operations",
    "fraud_risk",
}


# ─── Request Models ────────────────────────────────────────────────────────────

class TransactionEntry(BaseModel):
    transaction_id: str
    timestamp: str
    type: str
    amount: float
    counterparty: str
    status: str

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in TRANSACTION_TYPE_ENUM:
            raise ValueError(f"Invalid transaction type: {v}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in TRANSACTION_STATUS_ENUM:
            raise ValueError(f"Invalid transaction status: {v}")
        return v


class TicketRequest(BaseModel):
    ticket_id: str = Field(..., min_length=1)
    complaint: str = Field(..., min_length=1)
    language: Optional[str] = None
    channel: Optional[str] = None
    user_type: Optional[str] = None
    campaign_context: Optional[str] = None
    transaction_history: Optional[List[TransactionEntry]] = []
    metadata: Optional[Any] = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in LANGUAGE_ENUM:
            raise ValueError(f"Invalid language: {v}")
        return v

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in CHANNEL_ENUM:
            raise ValueError(f"Invalid channel: {v}")
        return v

    @field_validator("user_type")
    @classmethod
    def validate_user_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in USER_TYPE_ENUM:
            raise ValueError(f"Invalid user_type: {v}")
        return v

    @field_validator("complaint")
    @classmethod
    def validate_complaint_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("complaint must not be empty")
        return v


# ─── Response Models ───────────────────────────────────────────────────────────

class TicketResponse(BaseModel):
    ticket_id: str
    relevant_transaction_id: Optional[str] = None
    evidence_verdict: str
    case_type: str
    severity: str
    department: str
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: Optional[float] = None
    reason_codes: Optional[List[str]] = None


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[Any] = None
