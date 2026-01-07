from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.config.settings import settings
from src.config.logs_config import get_logger
from src.models.asr_models import ASRModelManager
from src.models.transcription_model_adapter import initialize_adapters

from src.api.endpoints.router.routers import api_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for the FastAPI application"""
    # Startup
    logger.info("Starting AI Structure Microservice API")

    # Initialize ASR models
    try:
        asr_manager = ASRModelManager()
        app.state.asr_manager = asr_manager
        logger.info("ASR models loaded successfully")

        # Initialize transcription adapters
        initialize_adapters(asr_manager)
        logger.info("Transcription adapters initialized")

    except Exception as e:
        logger.error(f"Failed to initialize models: {e}")

    yield

    # Shutdown
    logger.info("Shutting down AI Structure Microservice API")

    # Cleanup models
    if hasattr(app.state, "asr_manager"):
        app.state.asr_manager.unload_models()
        logger.info("ASR models unloaded")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""

    app = FastAPI(
        title="AI Structure Microservice API",
        description="API for AI Structure",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API router
    app.include_router(api_router, prefix=settings.API_PREFIX)

    # Health check endpoint
    @app.get("/")
    async def check():
        return {
            "status": "healthy",
            "service": "AI Structure Microservice",
        }

    logger.info("FastAPI application configured successfully")
    return app


# Create the application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        log_level=settings.LOG_LEVEL,
        # reload=settings.DEBUG,
    )
