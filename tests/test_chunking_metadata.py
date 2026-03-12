import pytest
from app.services.chunking_service import ChunkingService

@pytest.mark.asyncio
async def test_chunk_markdown_with_metadata():
    service = ChunkingService()
    markdown = """# Heading 1
Some text in heading 1.

## Heading 2
Text in heading 2 with a table.

| Col 1 | Col 2 |
|-------|-------|
| Val 1 | Val 2 |

### Heading 3
Text in heading 3 with code.

```python
print("hello")
```

![Image](path/to/image.png)
> <IMAGE_CONTEXTUAL_DESCRIPTION>This is a test image.</IMAGE_CONTEXTUAL_DESCRIPTION>
"""
    
    # We expect the chunking to return objects with metadata now
    # Since I haven't changed the code yet, this test will fail if I expect dicts
    # but it's a good way to see what we want.
    
    chunks = await service.chunk_markdown(markdown, max_chunk_tokens=100)
    
    assert len(chunks) > 0
    for chunk in chunks:
        # These are the fields we want to add
        assert "content" in chunk
        assert "metadata" in chunk
        assert "breadcrumbs" in chunk["metadata"]
        assert "content_length" in chunk["metadata"]
        assert "has_image" in chunk["metadata"]
        assert "has_table" in chunk["metadata"]
        assert "has_code" in chunk["metadata"]

    # Specific check for the table chunk
    table_chunk = [c for c in chunks if "Col 1" in c["content"]][0]
    assert table_chunk["metadata"]["has_table"] is True
    assert "Heading 1" in table_chunk["metadata"]["breadcrumbs"]
    assert "Heading 2" in table_chunk["metadata"]["breadcrumbs"]

    # Specific check for the code chunk
    code_chunk = [c for c in chunks if "print(" in c["content"]][0]
    assert code_chunk["metadata"]["has_code"] is True
    assert "Heading 3" in code_chunk["metadata"]["breadcrumbs"]

    # Specific check for image chunk
    image_chunk = [c for c in chunks if "path/to/image.png" in c["content"]][0]
    assert image_chunk["metadata"]["has_image"] is True
