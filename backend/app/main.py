import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis, ConnectionPool

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.rate_limit import RateLimiter, set_rate_limiter
from app.ai.vector_db.qdrant_client import QdrantVectorRepository

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    redis_pool = None
    redis_client = None

    # Initialize Redis connection pool
    if settings.RATE_LIMIT_ENABLED:
        try:
            redis_pool = ConnectionPool.from_url(
                f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
                if settings.REDIS_PASSWORD
                else f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}",
                max_connections=20,
                decode_responses=True,
                socket_timeout=0.1,
                socket_connect_timeout=0.1,
            )
            redis_client = Redis(connection_pool=redis_pool)
            # Test connection
            await redis_client.ping()

            # Initialize rate limiter
            rate_limiter = RateLimiter(redis_client)
            set_rate_limiter(rate_limiter)
            logger.info("Redis rate limiter initialized successfully")
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to initialize Redis rate limiter (rate limiting disabled): %s", exc
            )
            settings.RATE_LIMIT_ENABLED = False

    # Initialize Qdrant
    try:
        qdrant = QdrantVectorRepository()
        await qdrant.init_collections()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(
            "Failed to initialize Qdrant collections: %s", exc
        )

    yield

    # Shutdown
    if redis_client:
        try:
            await redis_client.aclose()
        except Exception:
            pass
    if redis_pool:
        try:
            await redis_pool.disconnect()
        except Exception:
            pass


is_prod = settings.ENVIRONMENT == "production"

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=None if is_prod else f"{settings.API_V1_STR}/openapi.json",
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
    lifespan=lifespan,
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }
