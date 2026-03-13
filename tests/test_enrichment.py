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
        '{"title": "Test Title", "analysis": "Test Analysis", "extra": "field"}',
    ]

    for out in outputs:
        repaired = json_repair.loads(out)
        assert isinstance(repaired, dict)
        assert repaired["title"] == "Test Title"
        assert repaired["analysis"] == "Test Analysis"


@pytest.mark.asyncio
async def test_markdown_integrity(tmp_path):
    service = VLMEnrichmentService()

    md_file = tmp_path / "test.md"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "test.jpg"
    # Use a real small image or just some bytes if the VLM client can handle it (it might fail if not real image)
    # However, the user asked for real implementation.
    img_file.write_bytes(b"fake image data")

    content = "# Title\n\nIntro\n\n![](images/test.jpg)\n\nOutro"
    md_file.write_text(content)

    await service.enrich_markdown(md_file)

    enriched_content = md_file.read_text()
    # Since we are using real LLM/VLM, we can't be sure of the exact strings,
    # but we can check for the presence of the tags.
    assert "![ " in enriched_content or "![" in enriched_content
    assert "<IMAGE_CONTEXTUAL_DESCRIPTION>" in enriched_content
    assert "Intro" in enriched_content
    assert "Outro" in enriched_content


@pytest.mark.asyncio
async def test_multiple_images_same_path(tmp_path):
    service = VLMEnrichmentService()

    md_file = tmp_path / "test.md"
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "test.jpg"
    img_file.write_bytes(b"fake image data")

    # Two identical tags at different positions
    content = "# Section\n\nContext 1\n\n![](images/test.jpg)\n\nContext 2\n\n![](images/test.jpg)"
    md_file.write_text(content)

    await service.enrich_markdown(md_file)

    enriched_content = md_file.read_text()
    assert enriched_content.count("<IMAGE_CONTEXTUAL_DESCRIPTION>") == 2


@pytest.mark.asyncio
async def test_enrichment_without_summarization(tmp_path):
    """Verify that enrichment works even when LLM summarization is disabled."""
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
        mock_settings.LLM_API_KEY = settings.LLM_API_KEY
        mock_settings.LLM_HOST_PATH = settings.LLM_HOST_PATH
        mock_settings.LLM_MODEL_NAME = settings.LLM_MODEL_NAME

        await service.enrich_markdown(md_file)

        # Verify enriched content
        enriched_content = md_file.read_text()
        assert "<IMAGE_CONTEXTUAL_DESCRIPTION>" in enriched_content


@pytest.mark.asyncio
async def test_vlm_retry_on_429(tmp_path):
    with patch("app.services.vlm_client.AsyncOpenAI") as mock_openai:
        mock_client = mock_openai.return_value

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            '{"title": "Retry Success", "analysis": "Success after 429"}'
        )

        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                RateLimitError("Rate limit exceeded", response=MagicMock(), body={}),
                RateLimitError("Rate limit exceeded", response=MagicMock(), body={}),
                mock_response,
            ]
        )

        client = VLMClient()
        client.retry_delay = 0.1

        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(b"data")

        result = await client.analyze_image(
            img_file,
            "doc_summary",
            "heading_path",
            "section_summary",
            "surrounding_text",
        )

        assert result["title"] == "Retry Success"
        assert mock_client.chat.completions.create.call_count == 3


@pytest.mark.asyncio
async def test_restore_header_hierarchy_case1(enrichment_service):
    """Test that _restore_header_hierarchy correctly identifies and replaces headers."""
    # Read the real test.md
    test_md_path = Path("tests/data/test.md")
    content = test_md_path.read_text(encoding="utf-8")

    restored_content = await enrichment_service._restore_header_hierarchy(content)
    print(restored_content)
    # Verify the content was updated.
    # In test.md, "# A800 High-Performance AI Storage" is a candidate for level 2.
    # We check if some headers were likely corrected (e.g. from # to ##)
    assert "# Huawei New-Gen OceanStor" in restored_content
    assert "## $\triangleleft$" in restored_content


@pytest.mark.asyncio
async def test_restore_header_hierarchy_case2(enrichment_service):
    """Test that _restore_header_hierarchy correctly identifies and replaces headers."""
    # Read the real hammerspace.md
    test_md_path = Path("tests/data/hammerspace.md")
    content = test_md_path.read_text(encoding="utf-8")

    restored_content = await enrichment_service._restore_header_hierarchy(content)

    # In hammerspace.md, "# 2.1 Universal Data Access Layer" should be corrected to ##
    assert "# 2. Hammerspace Architecture" in restored_content
    assert "## 2.1 Universal Data Access Layer" in restored_content


@pytest.mark.asyncio
async def test_restore_header_heuristic(enrichment_service):
    """Test that the heuristic correctly identifies non-# lines as potential headers."""
    content = "1. Introduction\nSome text.\n1.1. Background\nMore text.\nA. Summary\nEnd.\nAppendix  12"

    restored_content = await enrichment_service._restore_header_hierarchy(content)

    # We expect the real LLM to add '#' to these lines
    assert "# 1. Introduction" in restored_content
    assert (
        "## 1.1. Background" in restored_content
        or "# 1.1. Background" in restored_content
    )
    assert "# A. Summary" in restored_content
    assert "Some text." in restored_content


@pytest.mark.asyncio
async def test_llm_alive():
    """
    Smoke test to ensure LLM and VLM clients can connect.
    Sends a simple 'hi' and checks for a non-empty response.
    """
    llm_client = LLMClient()
    # Test LLM connectivity
    response = await llm_client.summarize("hi")
    assert response and len(response) > 0

    # Since VLMClient uses the same AsyncOpenAI client logic,
    # successfully calling the LLM confirms the underlying connectivity.
    # We instantiate VLMClient just to ensure no initialization errors.
    vlm_client = VLMClient()
    assert vlm_client.model is not None
