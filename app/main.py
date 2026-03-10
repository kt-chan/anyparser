import os
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.api.v1.process import router as parse_router
from app.api.v1.system import router as system_router
from app.core.config import settings
from app.utils.file_handler import cleanup_temp_dir
from loguru import logger

# Configure Logging
log_file = os.path.join(settings.LOGS_DIR, "main.log")
os.makedirs(settings.LOGS_DIR, exist_ok=True)
logger.add(log_file, rotation="500 MB", level="INFO")

async def daily_cleanup_task():
    """Background task to cleanup temp dir daily."""
    while True:
        try:
            logger.info("Running scheduled daily cleanup")
            cleanup_temp_dir()
        except Exception as e:
            logger.error(f"Scheduled cleanup failed: {e}")
        # Sleep for 24 hours
        await asyncio.sleep(24 * 3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start daily cleanup task if enabled
    cleanup_task = None
    if settings.ENABLE_DAILY_CLEANUP:
        cleanup_task = asyncio.create_task(daily_cleanup_task())
    else:
        logger.info("Daily maintenance cleanup is disabled")
    
    # Initialize MinerU SDK Environment Variables
    settings.setup_mineru_env()
    yield
    # Shutdown: Cancel the cleanup task if it was started
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            logger.info("Scheduled cleanup task cancelled")

app = FastAPI(title="MinerU PDF Parser Service", lifespan=lifespan)

# Include Routers
app.include_router(parse_router, prefix="/v1")
app.include_router(system_router, prefix="/v1")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
