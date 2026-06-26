import logging
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

from app.models.schemas import TicketRequest, TicketResponse, HealthResponse, ErrorResponse
from app.services.analyzer import analyze_ticket
from app.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Health"],
)
async def health_check():
    """Return service health status. Used by the judge harness to confirm readiness."""
    return HealthResponse(status="ok")


@router.post(
    "/analyze-ticket",
    response_model=TicketResponse,
    summary="Analyze a support ticket",
    tags=["Analysis"],
    responses={
        200: {"description": "Successful analysis"},
        400: {"model": ErrorResponse, "description": "Malformed input"},
        422: {"model": ErrorResponse, "description": "Semantically invalid input"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def analyze_ticket_endpoint(
    ticket: TicketRequest,
    db=Depends(get_db),
):
    """
    Analyze a customer support ticket using transaction history evidence.

    Returns a structured JSON response with:
    - Transaction identification
    - Evidence verdict (consistent / inconsistent / insufficient_data)
    - Case classification and routing
    - Safe customer reply
    """
    # Extra semantic validation
    if not ticket.complaint or not ticket.complaint.strip():
        raise HTTPException(
            status_code=422,
            detail="complaint field must not be empty or whitespace only",
        )

    try:
        result = await analyze_ticket(ticket, db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unhandled error analyzing ticket {ticket.ticket_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error. Please try again.",
        )
