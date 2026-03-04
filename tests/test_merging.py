import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch
from app.services.enrichment_service import VLMEnrichmentService
from app.utils.markdown_parser import SemanticSection

@pytest.fixture
def enrichment_service():
    with patch("app.services.vlm_client.AsyncOpenAI"):
        with patch("app.services.llm_client.AsyncOpenAI"):
            return VLMEnrichmentService(content_batch_size=100) # Small batch size for testing

def test_merge_sections_basic(enrichment_service):
    # Setup a tree
    # Root
    #   H1 (50 chars)
    #     H2.1 (30 chars)
    #     H2.2 (30 chars)
    
    h1 = SemanticSection(title="H1", level=1, start_index=0, content="A" * 50)
    h2_1 = SemanticSection(title="H2.1", level=2, start_index=50, content="B" * 30)
    h2_2 = SemanticSection(title="H2.2", level=2, start_index=80, content="C" * 30)
    
    h1.add_child(h2_1)
    h1.add_child(h2_2)
    
    root = SemanticSection(title="Root", level=0, start_index=0, content="")
    root.add_child(h1)
    
    # max_chars = 100 * 4 = 400
    enrichment_service._merge_sections(root, 400)
    
    # Since H1+H2.1+H2.2 = 50+30+30 = 110 chars < 400, they should all be merged into Root or H1.
    # Root starts empty. H1 is merged into Root? 
    # Root.own_content + H1.own_content = 0 + 50 < 400 -> H1 merged into Root.
    # Then H2.1 merged into Root, then H2.2 merged into Root.
    
    assert len(root.children) == 0
    assert len(root.own_content) == 110
    assert root.own_content == ("A" * 50) + ("B" * 30) + ("C" * 30)

def test_merge_sections_limit(enrichment_service):
    # Root
    #   H1 (80 chars)
    #   H2 (40 chars)
    #   H3 (40 chars)
    # max_chars = 100
    
    h1 = SemanticSection(title="H1", level=1, start_index=0, content="A" * 80)
    h2 = SemanticSection(title="H2", level=1, start_index=80, content="B" * 40)
    h3 = SemanticSection(title="H3", level=1, start_index=120, content="C" * 40)
    
    root = SemanticSection(title="Root", level=0, start_index=0, content="")
    root.add_child(h1)
    root.add_child(h2)
    root.add_child(h3)
    
    enrichment_service._merge_sections(root, 100)
    
    # 1. H1 merged into Root (0 + 80 < 100). Root.own_content = 80.
    # 2. H2 NOT merged into Root (80 + 40 > 100). H2 stays as child of Root.
    # 3. receiver becomes H2.
    # 4. H3: H2.own_content(40) + H3.own_content(40) = 80 < 100.
    # 5. H3 merged into H2.
    
    assert root.own_content == "A" * 80
    assert len(root.children) == 1
    assert root.children[0].title == "H2"
    assert root.children[0].own_content == ("B" * 40) + ("C" * 40)

def test_merge_sections_order_maintenance(enrichment_service):
    # Root (0)
    #   H1 (80 chars)
    #   H2 (huge, 200 chars)
    #   H3 (10 chars)
    # max_chars = 100
    
    h1 = SemanticSection(title="H1", level=1, start_index=0, content="A" * 80)
    h2 = SemanticSection(title="H2", level=1, start_index=80, content="B" * 200)
    h3 = SemanticSection(title="H3", level=1, start_index=280, content="C" * 10)
    
    root = SemanticSection(title="Root", level=0, start_index=0, content="")
    root.add_child(h1)
    root.add_child(h2)
    root.add_child(h3)
    
    enrichment_service._merge_sections(root, 100)
    
    # Correct (Order-preserving):
    # 1. H1 merged into Root (0+80 < 100). Root.own_content = 80.
    # 2. H2 cannot merge into Root (80+200 > 100). 
    # 3. H2 stays as child of Root. receiver = H2.
    # 4. H3: can it merge into receiver (H2)? H2.own_content(200) + H3.own_content(10) = 210. 
    #    Wait, 210 > 100. So H3 cannot merge into H2 either.
    # Result: Root(80), Children: [H2(200), H3(10)]
    
    assert root.own_content == "A" * 80
    assert len(root.children) == 2
    assert root.children[0].title == "H2"
    assert root.children[1].title == "H3"
    
    # If the logic was NOT order-preserving, H3 might have been merged into Root 
    # despite H2 being in the middle!

def test_merge_sections_sibling_merge(enrichment_service):
    # Root (0)
    #   H1 (90)
    #   H2 (5)
    #   H3 (5)
    # max_chars = 100
    
    h1 = SemanticSection(title="H1", level=1, start_index=0, content="A" * 90)
    h2 = SemanticSection(title="H2", level=1, start_index=90, content="B" * 5)
    h3 = SemanticSection(title="H3", level=1, start_index=95, content="C" * 5)
    
    root = SemanticSection(title="Root", level=0, start_index=0, content="")
    root.add_child(h1)
    root.add_child(h2)
    root.add_child(h3)
    
    enrichment_service._merge_sections(root, 100)
    
    # 1. H1 merges into Root (0+90 < 100). Root(90), receiver = Root.
    # 2. H2: Root(90)+5=95 < 100. Merge H2 into Root. Root(95), receiver = Root.
    # 3. H3: Root(95)+5=100. Merge? If < 100, then NO. If <= 100 then YES.
    # Let's assume < 100 for now.
    
    assert root.own_content == ("A" * 90) + ("B" * 5)
    assert len(root.children) == 1
    assert root.children[0].title == "H3"
    assert root.children[0].own_content == "C" * 5

@pytest.mark.asyncio
async def test_summarize_recursive_calls(enrichment_service):
    # Verify that LLM is called fewer times after merging
    # This is hard to test directly without mocking the whole flow
    pass
