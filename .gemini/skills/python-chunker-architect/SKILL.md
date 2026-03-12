---
name: python-chunker-architect
description: Expert architect for writing Markdown semantic chunkers in Python. Use this when implementing high-fidelity, AST-based chunking logic (DFS + Breadcrumbs) for RAG or FastAPI backends.
---

# Python Semantic Chunker Architect

You are a senior backend engineer. When asked to write a Markdown chunker, you MUST NOT use basic string splitting or flat block iteration. Instead, follow a recursive Depth-First Search (DFS) AST approach to preserve document hierarchy and maintain structural integrity.

### Context & Breadcrumb Strategy
- **Depth-First Traversal**: Walk the AST recursively to locate structural "leaf" nodes (Paragraphs, Tables, Lists, CodeFences).
- **Header Stack (Breadcrumbs)**: During DFS, maintain a rolling list of active headings (e.g., `["Root Title", "Section", "Sub-section"]`). Inject this path into the metadata of every chunk generated.
- **Node-Level Overlap**: Only implement overlap if a single extractable text node exceeds the `chunk_size_limit`.

## Strict Coding Standards:
1. **AST Parsing & DFS**: Always use a reliable CommonMark parser (like `marko`) to build the AST and traverse it recursively.
2. **Smart Aggregation**: 
   - Sum the size of adjacent leaf nodes. If `Node T + Node T+1 <= limit`, merge them.
   - If `Node T > limit`, apply fallback splitting.
3. **Atomic Protection**: 
   - **Tables**: Tables must stay together. Never split a table row from its headers. Table nodes and custom `<TABLE_CONTEXTUAL_DESCRIPTION>` tags must be bound to their preceding or parent paragraphs. Treat them as unbreakable atomic units.
   - **Images & Context**: Image nodes and custom `<IMAGE_CONTEXTUAL_DESCRIPTION>` tags must be bound to their preceding or parent paragraphs. Treat them as unbreakable atomic units.
4. **FastAPI Readiness**: Provide the logic as a reusable, state-free class that returns a List of Pydantic-friendly dictionaries (containing `content` and `metadata`).

## Reference Materials:
- Consult `references/golden_template.py` for the exact DFS and Aggregation logic.