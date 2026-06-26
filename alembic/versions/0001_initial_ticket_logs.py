"""Initial ticket_logs table

Revision ID: 0001
Revises:
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ticket_id", sa.String(128), nullable=False),
        sa.Column("complaint", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("channel", sa.String(64), nullable=True),
        sa.Column("user_type", sa.String(32), nullable=True),
        sa.Column("campaign_context", sa.String(128), nullable=True),
        sa.Column("transaction_history", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("relevant_transaction_id", sa.String(128), nullable=True),
        sa.Column("evidence_verdict", sa.String(32), nullable=True),
        sa.Column("case_type", sa.String(64), nullable=True),
        sa.Column("severity", sa.String(16), nullable=True),
        sa.Column("department", sa.String(64), nullable=True),
        sa.Column("agent_summary", sa.Text(), nullable=True),
        sa.Column("recommended_next_action", sa.Text(), nullable=True),
        sa.Column("customer_reply", sa.Text(), nullable=True),
        sa.Column("human_review_required", sa.Boolean(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reason_codes", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("processing_time_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ticket_logs_ticket_id"), "ticket_logs", ["ticket_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ticket_logs_ticket_id"), table_name="ticket_logs")
    op.drop_table("ticket_logs")
