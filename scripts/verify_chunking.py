import asyncio
import json
from pathlib import Path
from app.services.chunking_service import ChunkingService

async def test_chunking():
    service = ChunkingService()
    
    # Load sample markdown
    md_path = Path("tests/data/test.md")
    if not md_path.exists():
        print(f"Error: {md_path} not found")
        return
        
    with open(md_path, "r", encoding="utf-8") as f:
        markdown_content = f.read()
    
    print(f"Original content length: {len(markdown_content)} characters")
    
    # Test with a chunk size limit
    chunk_size = 500
    print(f"Chunking with limit: {chunk_size} tokens...")
    
    chunks = await service.chunk_markdown(markdown_content, chunk_size)
    
    print(f"Generated {len(chunks)} chunks.")
    
    # Display the first few chunks and their metadata
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n--- Chunk {i+1} ---")
        print(f"Tokens: {chunk['metadata']['tokens']}")
        print(f"Breadcrumbs: {' > '.join(chunk['metadata']['breadcrumbs'])}")
        print(f"Has Table: {chunk['metadata']['has_table']}")
        print(f"Has Image: {chunk['metadata']['has_image']}")
        print(f"Content snippet: {chunk['content'][:200]}...")

    # Save to a temporary file for inspection if needed
    output_path = Path("temp/test_chunk_output.json")
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    print(f"\nFull output saved to {output_path}")

if __name__ == "__main__":
    asyncio.run(test_chunking())
