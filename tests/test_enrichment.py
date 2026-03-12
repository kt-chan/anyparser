import pytest
import re
import json
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.enrichment_service import VLMEnrichmentService
from app.services.vlm_client import VLMClient
from app.services.llm_client import LLMClient
from openai import RateLimitError
import json_repair

@pytest.fixture
def enrichment_service():
    with patch("app.services.vlm_client.AsyncOpenAI"):
        with patch("app.services.llm_client.AsyncOpenAI"):
            return VLMEnrichmentService()

def test_regex_extraction(enrichment_service):
    content = "Some text ![](images/img1.jpg) and more text ![](images/img2.png)"
    matches = list(enrichment_service.image_pattern.finditer(content))
    assert len(matches) == 2
    assert matches[0].group(1) == "images/img1.jpg"
    assert matches[1].group(1) == "images/img2.png"

def test_context_window(enrichment_service):
    # Requirement: 500 characters (250 before, 250 after)
    prefix = "A" * 300
    suffix = "B" * 300
    content = f"{prefix}![](images/img1.jpg){suffix}"
    
    match = next(enrichment_service.image_pattern.finditer(content))
    # In VLMEnrichmentService, we use 250 before and 250 after
    start_ctx = max(0, match.start() - 250)
    end_ctx = min(len(content), match.end() + 250)
    context = content[start_ctx:end_ctx]
    
    assert len(context) == 250 + len(match.group(0)) + 250
    assert context.startswith("A" * 250)
    assert context.endswith("B" * 250)

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
        with patch("app.services.llm_client.AsyncOpenAI"):
            service = VLMEnrichmentService()
    
    md_file = tmp_path / "test.md"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "test.jpg"
    img_file.write_bytes(b"fake image data")
    
    content = "# Title\n\nIntro\n\n![](images/test.jpg)\n\nOutro"
    md_file.write_text(content)
    
    mock_result = {"title": "A technical title", "analysis": "Detailed analysis."}
    
    # Mock LLM and VLM calls
    with patch.object(service.llm_client, 'summarize', return_value="Summary"):
        with patch.object(service.vlm_client, 'analyze_image', return_value=mock_result):
            await service.enrich_markdown(md_file)
    
    enriched_content = md_file.read_text()
    assert "![A technical title](images/test.jpg)" in enriched_content
    assert "> <IMAGE_CONTEXTUAL_DESCRIPTION>Detailed analysis.</IMAGE_CONTEXTUAL_DESCRIPTION>" in enriched_content
    assert "Intro" in enriched_content
    assert "Outro" in enriched_content

@pytest.mark.asyncio
async def test_multiple_images_same_path(tmp_path):
    with patch("app.services.vlm_client.AsyncOpenAI"):
        with patch("app.services.llm_client.AsyncOpenAI"):
            service = VLMEnrichmentService()
    
    md_file = tmp_path / "test.md"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "test.jpg"
    img_file.write_bytes(b"fake image data")
    
    # Two identical tags at different positions
    content = "# Section\n\nContext 1\n\n![](images/test.jpg)\n\nContext 2\n\n![](images/test.jpg)"
    md_file.write_text(content)
    
    mock_results = [
        {"title": "Title 1", "analysis": "Analysis 1"},
        {"title": "Title 2", "analysis": "Analysis 2"}
    ]
    
    with patch.object(service.llm_client, 'summarize', return_value="Summary"):
        with patch.object(service.vlm_client, 'analyze_image', side_effect=mock_results):
            await service.enrich_markdown(md_file)
    
    enriched_content = md_file.read_text()
    assert "![Title 1](images/test.jpg)" in enriched_content
    assert "Analysis 1" in enriched_content
    assert "![Title 2](images/test.jpg)" in enriched_content
    assert "Analysis 2" in enriched_content

@pytest.mark.asyncio
async def test_enrichment_without_summarization(tmp_path):
    """Verify that enrichment works even when LLM summarization is disabled."""
    with patch("app.services.vlm_client.AsyncOpenAI"):
        with patch("app.services.llm_client.AsyncOpenAI"):
            service = VLMEnrichmentService()
    
    md_file = tmp_path / "no_sum.md"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    (img_dir / "test.jpg").write_bytes(b"data")
    
    content = "# Section A\nSome text.\n![](images/test.jpg)"
    md_file.write_text(content)
    
    # Mock settings to disable summarization
    with patch("app.services.enrichment_service.settings") as mock_settings:
        mock_settings.ENABLE_LLM_SUMMARIZATION = False
        mock_settings.LOGS_DIR = str(tmp_path / "logs")
        
        mock_vlm_result = {"title": "Title", "analysis": "Analysis"}
        
        # Mock LLM summarize to ensure it's NOT called
        with patch.object(service.llm_client, 'summarize', side_effect=Exception("LLM should not be called")):
            with patch.object(service.vlm_client, 'analyze_image', return_value=mock_vlm_result) as mock_analyze:
                root = await service.enrich_markdown(md_file)
                
                # Verify LLM wasn't called
                # Verify VLM was called with raw content as section summary
                mock_analyze.assert_called_once()
                args, kwargs = mock_analyze.call_args
                # section_summary should be a snippet of raw content
                assert "Some text" in kwargs["section_summary"]
                
                # Verify enriched content
                enriched_content = md_file.read_text()
                assert "![Title](images/test.jpg)" in enriched_content
                assert "Analysis" in enriched_content

@pytest.mark.asyncio
async def test_vlm_retry_on_429(tmp_path):
    with patch("app.services.vlm_client.AsyncOpenAI") as mock_openai:
        mock_client = mock_openai.return_value
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"title": "Retry Success", "analysis": "Success after 429"}'
        
        mock_client.chat.completions.create = AsyncMock(side_effect=[
            RateLimitError("Rate limit exceeded", response=MagicMock(), body={}),
            RateLimitError("Rate limit exceeded", response=MagicMock(), body={}),
            mock_response
        ])
        
        client = VLMClient()
        client.retry_delay = 0.1
        
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"data")
        
        result = await client.analyze_image(
            img_file, 
            "doc_summary", 
            "heading_path", 
            "section_summary", 
            "surrounding_text"
        )
        
        assert result["title"] == "Retry Success"
        assert mock_client.chat.completions.create.call_count == 3
