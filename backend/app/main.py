import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis, ConnectionPool
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.pubsub import pubsub_manager
from app.core.rate_limit import RateLimiter, set_rate_limiter
from app.ai.vector_db.qdrant_client import QdrantVectorRepository

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Minimal security headers middleware for API responses.

    Adds safe headers without assuming TLS or proxy infrastructure.
    Does not add HSTS, HTTPS redirects, or proxy-header trust.
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Safe headers for all responses (including errors)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")

        # CSP for API: no browser resources expected from API endpoints.
        # Skip restrictive CSP for development documentation routes (/docs, /redoc)
        # to allow Swagger UI / ReDoc to load scripts and styles.
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")

        # Do NOT add HSTS, HTTPS redirects, or proxy-header trust
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    redis_pool = None
    redis_client = None

    # Initialize Redis connection pool (always for JWT revocation)
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

        # Store Redis client in app state for shared access
        app.state.redis = redis_client
        logger.info("Redis client initialized for application infrastructure")

        # Initialize rate limiter only if enabled
        if settings.RATE_LIMIT_ENABLED:
            rate_limiter = RateLimiter()
            set_rate_limiter(rate_limiter)
            logger.info("Redis rate limiter initialized successfully")
        else:
            logger.info("Rate limiting disabled (RATE_LIMIT_ENABLED=false)")

    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to initialize Redis client: %s", exc
        )
        redis_client = None
        redis_pool = None
        app.state.redis = None

    # Initialize Qdrant
    try:
        qdrant = QdrantVectorRepository()
        await qdrant.init_collections()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(
            "Failed to initialize Qdrant collections: %s", exc
        )

    # Initialize PubSub manager for real-time notifications
    try:
        await pubsub_manager.connect()
        logger.info("PubSub manager initialized for real-time notifications")
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error(
            "Failed to initialize PubSub manager: %s", exc
        )

    yield

    # Shutdown
    try:
        await pubsub_manager.disconnect()
        logger.info("PubSub manager disconnected")
    except Exception:
        pass

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

# Set up Security Headers middleware (after CORS to preserve CORS headers)
app.add_middleware(SecurityHeadersMiddleware)

# Include API Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/")
async def root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "docs": "/docs",
        "health": f"{settings.API_V1_STR}/health"
    }
