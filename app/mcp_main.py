import os
from typing import List, Dict, Any
from loguru import logger
from fastmcp import FastMCP
from app.services.chunking_service import ChunkingService

mcp = FastMCP("MinerU Smart Chunking")
chunking_service = ChunkingService()

@mcp.tool()
async def smart_chunking(pdf_base64: str) -> List[Dict[str, Any]]:
    """
    Parse a PDF file and return multi-modal chunks (text and images with VLM-enriched descriptions).
    
    Args:
        pdf_base64: Base64 encoded string of the PDF file.
    """
    return await chunking_service.process_pdf_to_chunks(pdf_base64)

if __name__ == "__main__":
    # Allow choosing transport via environment variable
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    logger.info(f"Starting MCP server with transport: {transport}")
    mcp.run(transport=transport)
