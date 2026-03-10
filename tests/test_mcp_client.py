import sys
import os
import pytest
import base64
from pathlib import Path
from app.mcp_main import smart_chunking

# Add fallback path for environment with mixed library locations if needed
user_site = os.path.expanduser("~\\AppData\\Roaming\\Python\\Python313\\site-packages")
if user_site not in sys.path and os.path.exists(user_site):
    sys.path.append(user_site)

@pytest.fixture
def real_pdf_base64():
    pdf_path = Path("tests/test.pdf")
    if not pdf_path.exists():
        pytest.fail(f"Test PDF not found at {pdf_path}")
    with open(pdf_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

@pytest.mark.asyncio
async def test_smart_chunking_real(real_pdf_base64):
    """
    Integration test for smart_chunking using a real PDF and real services (MinerU & VLM).
    Requires a valid .env file with MinerU and VLM configuration.
    """
    # Call the tool with real PDF data
    # This will use the real mineru_client and vlm_enrichment_service
    result = await smart_chunking(real_pdf_base64)
    
    # Assertions
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    assert len(result) > 0, "Result list is empty"
    
    # Check for errors in the output
    for chunk in result:
        if chunk.get("type") == "error":
            pytest.fail(f"Smart chunking failed with error: {chunk.get('content')}")
            
    # Basic validation of chunks
    has_text = any(chunk["type"] == "text" for chunk in result)
    # We can't strictly assert images because it depends on the PDF content,
    # but for tests/test.pdf we expect some text at least.
    assert has_text, "No text chunks found in the output"
    
    # Log the number of chunks found for debugging
    print(f"\nSuccessfully processed PDF into {len(result)} chunks.")
    for i, chunk in enumerate(result[:3]): # Print first 3 chunks metadata
        print(f"Chunk {i}: type={chunk['type']}, metadata={chunk.get('metadata')}")

@pytest.mark.asyncio
async def test_smart_chunking_invalid_base64():
    """Test with invalid base64 string"""
    result = await smart_chunking("not-a-base64-string")
    assert len(result) == 1
    assert result[0]["type"] == "error"
    assert "Internal server error" in result[0]["content"]
