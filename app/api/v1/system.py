from fastapi import APIRouter, HTTPException
from app.utils.file_handler import cleanup_temp_dir
from loguru import logger

router = APIRouter()

@router.post("/system/cleanup")
async def trigger_cleanup():
    """
    Manually triggers cleanup of the temporary directory.
    """
    try:
        logger.info("Manual cleanup triggered via API")
        cleanup_temp_dir()
        return {"status": "success", "message": "Temporary directory cleaned up"}
    except Exception as e:
        logger.error(f"Manual cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
