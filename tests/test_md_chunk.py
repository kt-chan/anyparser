import pytest
from fastapi.testclient import TestClient
from app.main import app
from pathlib import Path
from unittest.mock import MagicMock, patch

client = TestClient(app)

def test_chunk_markdown_file_success():
    """Test successful markdown file chunking."""
    md_content = "# Heading 1\n\nThis is a paragraph.\n\n## Heading 2\n\nAnother paragraph here."
    files = {"file": ("test.md", md_content.encode("utf-8"), "text/markdown")}
    
    response = client.post("/v1/md/chunk", files=files, data={"chunk_size": 2000})
    
    assert response.status_code == 200
    assert "chunks" in response.json()
    chunks = response.json()["chunks"]
    assert len(chunks) > 0
    # Check if first chunk contains content from md_content
    assert any("Heading 1" in str(chunk["metadata"]["breadcrumbs"]) for chunk in chunks)

def test_chunk_markdown_file_default_size():
    """Test markdown file chunking with default size."""
    md_content = "# Heading 1\n\n" + "Word " * 100
    files = {"file": ("test.md", md_content.encode("utf-8"), "text/markdown")}
    
    # Not passing chunk_size, should use default 2000
    response = client.post("/v1/md/chunk", files=files)
    
    assert response.status_code == 200
    assert "chunks" in response.json()

def test_chunk_markdown_file_wrong_extension_warning():
    """Test that it still works even with wrong extension (logs a warning)."""
    md_content = "# Heading 1\n\nContent"
    files = {"file": ("test.txt", md_content.encode("utf-8"), "text/plain")}
    
    response = client.post("/v1/md/chunk", files=files)
    
    assert response.status_code == 200
    assert "chunks" in response.json()
