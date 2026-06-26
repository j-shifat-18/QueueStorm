"""
Vercel entry point — imports and re-exports the FastAPI app.
Vercel looks for an ASGI `app` object in this file.
"""
from app.main import app  # noqa: F401
