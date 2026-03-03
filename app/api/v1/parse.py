from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from mineru.cli.common import aio_do_parse, read_fn
from app.services.mineru_client import MinerUWrapper
from app.utils.file_handler import save_upload_file, cleanup_file
from app.utils.archive import compress_folder
from loguru import logger
from pathlib import Path
import shutil
import os

router = APIRouter()
mineru_client = MinerUWrapper()

def cleanup_job_files(paths: list[Path]):
    """Background task to cleanup temporary files and directories."""
    for path in paths:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            logger.info(f"Cleaned up: {path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup {path}: {e}")

@router.post("/pdf/parse")
async def parse_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Endpoint to parse a PDF file.
    Accepts binary PDF upload.
    Returns a .tar.gz archive of the parsing results.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    logger.info(f"Received PDF parsing request: {file.filename}")
    
    local_pdf_path = save_upload_file(file)
    output_dir = None
    tar_path = None
    
    try:
        # Process the PDF using MinerU SDK (Asynchronously)
        output_dir = await mineru_client.process_pdf(local_pdf_path)
        
        # Tar the results
        tar_name = f"{local_pdf_path.stem}_results.tar.gz"
        tar_path = Path(local_pdf_path.parent) / tar_name
        compress_folder(output_dir, tar_path)
        
        # Add background cleanup task
        # We cleanup the uploaded PDF, the output dir, and eventually the tar file
        # BUT we return the tar file first.
        background_tasks.add_task(cleanup_job_files, [local_pdf_path, output_dir.parent, tar_path])
        
        # Return the tar file as response
        return FileResponse(
            path=str(tar_path),
            media_type="application/gzip",
            filename=f"{file.filename}_results.tar.gz"
        )
    except Exception as e:
        logger.error(f"Error parsing PDF: {e}")
        # Cleanup on failure
        paths_to_cleanup = [local_pdf_path]
        if output_dir: paths_to_cleanup.append(output_dir.parent)
        if tar_path: paths_to_cleanup.append(tar_path)
        cleanup_job_files(paths_to_cleanup)
        raise HTTPException(status_code=500, detail=str(e))
