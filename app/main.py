import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.core.config import settings
from app.api.routes import router
from app.db.database import init_db_engine, create_tables

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("QueueStorm Investigator starting up...")

    # Initialize database if URL is provided
    if settings.DATABASE_URL:
        try:
            init_db_engine(settings.DATABASE_URL)
            await create_tables()
            logger.info("Database ready.")
        except Exception as e:
            logger.warning(f"Database initialization failed (continuing without DB): {e}")
    else:
        logger.warning("DATABASE_URL not set — running without database persistence.")

    yield

    logger.info("QueueStorm Investigator shutting down.")


# ── App instance ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="QueueStorm Investigator",
    description=(
        "AI-powered support ticket analyzer for digital finance platforms. "
        "Classifies, routes, and investigates customer complaints using "
        "transaction evidence and Gemini AI."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request timing middleware ──────────────────────────────────────────────────
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    process_time = (time.time() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{process_time:.1f}"
    return response


# ── Exception handlers ─────────────────────────────────────────────────────────
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    # Sanitize: never expose internal paths or secrets
    safe_errors = [
        {"field": ".".join(str(loc) for loc in e.get("loc", [])), "message": e.get("msg", "")}
        for e in errors
    ]
    return JSONResponse(
        status_code=400,
        content={"error": "Validation error", "detail": safe_errors},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=422,
        content={"error": str(exc)},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error. Please try again."},
    )


# ── Include API routes ─────────────────────────────────────────────────────────
app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
