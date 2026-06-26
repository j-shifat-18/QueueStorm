from sqlalchemy import Column, String, Boolean, Float, Text, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from app.db.database import Base


class TicketLog(Base):
    """
    Persists every analysis request and response for audit, analytics,
    and debugging purposes.
    """
    __tablename__ = "ticket_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(String(128), nullable=False, index=True)
    complaint = Column(Text, nullable=False)
    language = Column(String(16), nullable=True)
    channel = Column(String(64), nullable=True)
    user_type = Column(String(32), nullable=True)
    campaign_context = Column(String(128), nullable=True)

    # Stored as JSON
    transaction_history = Column(JSON, nullable=True)

    # Response fields
    relevant_transaction_id = Column(String(128), nullable=True)
    evidence_verdict = Column(String(32), nullable=True)
    case_type = Column(String(64), nullable=True)
    severity = Column(String(16), nullable=True)
    department = Column(String(64), nullable=True)
    agent_summary = Column(Text, nullable=True)
    recommended_next_action = Column(Text, nullable=True)
    customer_reply = Column(Text, nullable=True)
    human_review_required = Column(Boolean, nullable=True)
    confidence = Column(Float, nullable=True)
    reason_codes = Column(JSON, nullable=True)

    # Meta
    processing_time_ms = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
