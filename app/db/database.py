import logging
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

logger = logging.getLogger(__name__)

# asyncpg only accepts a specific set of connection parameters.
# These are the query-string params it CANNOT handle — strip them from the URL
# and convert the ones we care about into connect_args instead.
_UNSUPPORTED_PARAMS = {"sslmode", "channel_binding", "connect_timeout", "application_name"}


def get_async_db_url(url: str) -> tuple[str, dict]:
    """
    Convert a standard postgres:// URL to postgresql+asyncpg://, strip any
    query params that asyncpg doesn't understand, and return the cleaned URL
    together with a connect_args dict that asyncpg does understand.
    """
    # Normalise scheme
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parsed = urlparse(url)
    params = parse_qs(parsed.query, keep_blank_values=True)

    connect_args: dict = {}

    # Map sslmode → ssl connect_arg
    sslmode = params.pop("sslmode", [None])[0]
    if sslmode in ("require", "verify-full", "verify-ca"):
        connect_args["ssl"] = "require"
    elif sslmode == "disable":
        connect_args["ssl"] = False

    # Drop all other unsupported params
    for param in _UNSUPPORTED_PARAMS:
        params.pop(param, None)

    # Rebuild the clean URL
    clean_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url = urlunparse(parsed._replace(query=clean_query))

    return clean_url, connect_args


Base = declarative_base()
engine = None
async_session_maker = None


def init_db_engine(database_url: str):
    global engine, async_session_maker
    async_url, connect_args = get_async_db_url(database_url)
    engine = create_async_engine(
        async_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args=connect_args,
    )
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    logger.info("Database engine initialized.")


async def get_db():
    """Yield a database session, or None if the database is not initialized."""
    if async_session_maker is None:
        yield None
        return
    async with async_session_maker() as session:
        yield session


async def create_tables():
    if engine is None:
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified.")
