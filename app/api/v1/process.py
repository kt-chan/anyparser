from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.services.mineru_client import MinerUWrapper
from app.services.enrichment_service import VLMEnrichmentService
from app.services.chunking_service import ChunkingService
from app.utils.file_handler import save_upload_file, cleanup_file
from app.utils.archive import compress_folder
from loguru import logger
from pathlib import Path
from typing import List
import shutil
import base64
import asyncio

router = APIRouter()
mineru_client = MinerUWrapper()
vlm_enrichment_service = VLMEnrichmentService()
chunking_service = ChunkingService()

class ChunkRequest(BaseModel):
    markdown: str = Field(..., description="The markdown string to chunk")
    chunk_size: int = Field(1000, description="The maximum size of each chunk (in tokens)", gt=0)

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
        
        # Enrich the generated Markdown files with VLM analysis
        md_files = list(output_dir.rglob("*.md"))
        if md_files:
            logger.info(f"Enriching {len(md_files)} markdown files in {output_dir}")
            enrichment_tasks = [vlm_enrichment_service.enrich_markdown(md_file) for md_file in md_files]
            await asyncio.gather(*enrichment_tasks)
        
        # Tar the results
        tar_name = f"{local_pdf_path.stem}_results.tar.gz"
        tar_path = Path(local_pdf_path.parent) / tar_name
        compress_folder(output_dir, tar_path)
        
        # Add background cleanup task
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

@router.post("/pdf/chunk")
async def chunk_pdf(file: UploadFile = File(...)):
    """
    Endpoint to parse a PDF file and return multi-modal chunks.
    Accepts binary PDF upload.
    Returns a list of multi-modal chunks (text and images with descriptions).
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    logger.info(f"Received PDF chunking request: {file.filename}")
    
    try:
        # Read file bytes and encode to base64 for ChunkingService
        file_bytes = await file.read()
        pdf_base64 = base64.b64encode(file_bytes).decode("utf-8")
        
        # Process chunks
        chunks = await chunking_service.process_pdf_to_chunks(pdf_base64)
        
        # Check for errors in service output
        if chunks and chunks[0].get("type") == "error":
             raise HTTPException(status_code=500, detail=chunks[0].get("content"))
             
        return chunks
    except Exception as e:
        logger.error(f"Error chunking PDF: {e}")
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chunk")
async def chunk_markdown(request: ChunkRequest):
    """
    Endpoint to chunk a markdown string into semantic parts.
    """
    logger.info(f"Received markdown chunking request")
    try:
        chunks = await chunking_service.chunk_markdown(request.markdown, request.chunk_size)
        return {"chunks": chunks}
    except Exception as e:
        logger.error(f"Error chunking markdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))
