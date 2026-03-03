import pytest
import re
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.vlm_enrichment_service import VLMEnrichmentService
from app.services.vlm_client import VLMClient
from openai import RateLimitError
import json_repair

@pytest.fixture
def enrichment_service():
    with patch("app.services.vlm_client.AsyncOpenAI"):
        return VLMEnrichmentService()

def test_regex_extraction(enrichment_service):
    content = "Some text ![](images/img1.jpg) and more text ![](images/img2.png)"
    matches = list(enrichment_service.image_pattern.finditer(content))
    assert len(matches) == 2
    assert matches[0].group(1) == "images/img1.jpg"
    assert matches[1].group(1) == "images/img2.png"

def test_context_window(enrichment_service):
    prefix = "A" * 600
    suffix = "B" * 600
    content = f"{prefix}![](images/img1.jpg){suffix}"
    
    match = next(enrichment_service.image_pattern.finditer(content))
    start_ctx = max(0, match.start() - 500)
    end_ctx = min(len(content), match.end() + 500)
    context = content[start_ctx:end_ctx]
    
    # Context should be 500 before + tag length + 500 after
    assert len(context) == 500 + len(match.group(0)) + 500
    assert context.startswith("A" * 500)
    assert context.endswith("B" * 500)

def test_vlm_json_parsing_logic():
    # Test how we handle various VLM outputs using json_repair
    outputs = [
        '{"title": "Test Title", "analysis": "Test Analysis"}',
        '```json\n{"title": "Test Title", "analysis": "Test Analysis"}\n```',
        'Here is the JSON: {"title": "Test Title", "analysis": "Test Analysis"}',
        '{"title": "Test Title", "analysis": "Test Analysis", "extra": "field"}'
    ]
    
    for out in outputs:
        repaired = json_repair.loads(out)
        assert isinstance(repaired, dict)
        assert repaired["title"] == "Test Title"
        assert repaired["analysis"] == "Test Analysis"

@pytest.mark.asyncio
async def test_markdown_integrity(tmp_path):
    with patch("app.services.vlm_client.AsyncOpenAI"):
        service = VLMEnrichmentService()
    
    md_file = tmp_path / "test.md"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "test.jpg"
    img_file.write_bytes(b"fake image data")
    
    content = "Intro\n\n![](images/test.jpg)\n\nOutro"
    md_file.write_text(content)
    
    mock_result = {"title": "A technical title", "analysis": "Detailed analysis."}
    
    with patch.object(service.client, 'analyze_image', return_value=mock_result):
        await service.enrich_markdown(md_file)
    
    enriched_content = md_file.read_text()
    assert "![A technical title](images/test.jpg)" in enriched_content
    assert "> **Contextual Description:** Detailed analysis." in enriched_content
    assert "Intro" in enriched_content
    assert "Outro" in enriched_content

@pytest.mark.asyncio
async def test_multiple_images_same_path(tmp_path):
    with patch("app.services.vlm_client.AsyncOpenAI"):
        service = VLMEnrichmentService()
    
    md_file = tmp_path / "test.md"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "test.jpg"
    img_file.write_bytes(b"fake image data")
    
    # Two identical tags at different positions
    content = "Context 1\n\n![](images/test.jpg)\n\nContext 2\n\n![](images/test.jpg)"
    md_file.write_text(content)
    
    # We'll return different results for each call to verify they are handled independently
    mock_results = [
        {"title": "Title 1", "analysis": "Analysis 1"},
        {"title": "Title 2", "analysis": "Analysis 2"}
    ]
    
    with patch.object(service.client, 'analyze_image', side_effect=mock_results):
        await service.enrich_markdown(md_file)
    
    enriched_content = md_file.read_text()
    assert "![Title 1](images/test.jpg)" in enriched_content
    assert "Analysis 1" in enriched_content
    assert "![Title 2](images/test.jpg)" in enriched_content
    assert "Analysis 2" in enriched_content

@pytest.mark.asyncio
async def test_vlm_retry_on_429(tmp_path):
    with patch("app.services.vlm_client.AsyncOpenAI") as mock_openai:
        # Configure mock client
        mock_client = mock_openai.return_value
        
        # Mock create to fail then succeed
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"title": "Retry Success", "analysis": "Success after 429"}'
        
        # Setup side effect: 2 failures followed by 1 success
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            RateLimitError("Rate limit exceeded", response=MagicMock(), body={}),
            RateLimitError("Rate limit exceeded", response=MagicMock(), body={}),
            mock_response
        ])
        
        client = VLMClient()
        client.retry_delay = 0.1 # Fast test
        
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"data")
        
        result = await client.analyze_image(img_file, "context")
        
        assert result["title"] == "Retry Success"
        assert mock_client.chat.completions.create.call_count == 3
