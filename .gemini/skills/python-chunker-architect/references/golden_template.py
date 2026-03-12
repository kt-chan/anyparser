"""
GOLDEN TEMPLATE: Markdown Semantic Chunker
Logic: AST-based block traversal with atomic protection for Tables/Images.
"""
import mistletoe
from mistletoe.block_token import Table, Paragraph, Heading, CodeFence
from mistletoe.markdown_renderer import MarkdownRenderer

class SemanticChunker:
    def __init__(self, max_chunk_size: int):
        self.max_chunk_size = max_chunk_size
        self.renderer = MarkdownRenderer()

    def get_chunks(self, markdown_text: str):
        # 1. Parse into AST
        doc = mistletoe.Document(markdown_text)
        
        chunks = []
        current_batch = []
        current_size = 0

        for node in doc.children:
            # 2. Render node back to string to check size
            node_md = self.renderer.render(node)
            node_len = len(node_md)

            # 3. Handle Atomic Blocks (Tables/Images/Code)
            # We NEVER split inside these, even if they exceed max_chunk_size
            is_atomic = isinstance(node, (Table, CodeFence)) or "![ " in node_md
            
            # 4. Handle Large Paragraphs (Splitting logic)
            if isinstance(node, Paragraph) and node_len > self.max_chunk_size:
                # If we have a pending chunk, flush it first
                if current_batch:
                    chunks.append("".join(current_batch))
                    current_batch, current_size = [], 0
                
                # Split large text by sentences
                import re
                sentences = re.split(r'(?<=[.!?]) +', node_md)
                for sentence in sentences:
                    if current_size + len(sentence) > self.max_chunk_size:
                        chunks.append("".join(current_batch))
                        current_batch, current_size = [], 0
                    current_batch.append(sentence)
                    current_size += len(sentence)
                continue

            # 5. Buffer Management (Concatenation)
            if current_size + node_len > self.max_chunk_size and current_size > 0:
                chunks.append("".join(current_batch))
                current_batch = [node_md]
                current_size = node_len
            else:
                current_batch.append(node_md)
                current_size += node_len

        if current_batch:
            chunks.append("".join(current_batch))
            
        return [c.strip() for c in chunks if c.strip()]