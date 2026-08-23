from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.core.config import settings
from app.ai.vector_db.qdrant_client import QdrantVectorRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        qdrant = QdrantVectorRepository()
        await qdrant.init_collections()
    except Exception as exc:
        # Log the initialization failure but don't crash the application
        # The application should still start even if Qdrant is temporarily unavailable
        import logging
        logging.getLogger(__name__).error(
            "Failed to initialize Qdrant collections: %s", exc
        )
    yield
    # Shutdown (no cleanup needed for Qdrant)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
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
