"""
GOLDEN TEMPLATE: Markdown Semantic Chunker (DFS + Breadcrumbs)
Logic: AST-based Depth-First Search traversal with atomic protection for Tables/Images.
"""
import re
from typing import List, Dict, Any
import marko
from marko.block import Document, Heading, Paragraph, List as MDList, Quote, FencedCode, HTMLBlock
from marko.ext.gfm import gfm # For table support
from marko.md_renderer import MarkdownRenderer

class ASTSemanticChunker:
    def __init__(self, chunk_size_limit: int = 1024):
        self.chunk_size_limit = chunk_size_limit
        # Initialize marko with GFM for Table support and a Markdown renderer to convert nodes back to text
        self.md = marko.Markdown(extensions=['gfm'], renderer=MarkdownRenderer)

    def get_chunks(self, markdown_text: str) -> List[Dict[str, Any]]:
        ast = self.md.parse(markdown_text)
        
        # 1. DFS Traversal to extract semantic units
        semantic_units = []
        self._dfs_traverse(ast, header_stack=[], units_accumulator=semantic_units)
        
        # 2. Smart Aggregation & Splitting
        return self._aggregate_units(semantic_units)

    def _dfs_traverse(self, node: Any, header_stack: List[str], units_accumulator: List[Dict]):
        """Recursively walks the AST, updating breadcrumbs and extracting leaf units."""
        
        # Update breadcrumbs if we hit a Heading
        if isinstance(node, Heading):
            level = node.level
            heading_text = self.md.render(node).strip().strip('#').strip()
            
            # Pop headers that are at the same or deeper level
            header_stack[:] = header_stack[:level-1]
            header_stack.append(heading_text)
            return # Headings become metadata, we don't usually chunk them alone

        # Identify extractable leaf blocks
        is_leaf_block = isinstance(node, (Paragraph, MDList, Quote, FencedCode, HTMLBlock))
        is_table = type(node).__name__ == 'Table' # GFM Table

        if is_leaf_block or is_table:
            rendered_text = self.md.render(node).strip()
            if rendered_text:
                units_accumulator.append({
                    "content": rendered_text,
                    "type": type(node).__name__,
                    "breadcrumbs": list(header_stack),
                    "is_atomic": is_table or "<IMAGE_CONTEXTUAL_DESCRIPTION>" in rendered_text
                })
            return

        # Continue DFS for children if not a designated leaf block
        if hasattr(node, 'children') and isinstance(node.children, list):
            for child in node.children:
                self._dfs_traverse(child, header_stack, units_accumulator)

    def _aggregate_units(self, units: List[Dict]) -> List[Dict[str, Any]]:
        """Merges small units and force-splits excessively large text nodes."""
        chunks = []
        current_chunk_content = ""
        current_breadcrumbs = []
        
        def flush():
            nonlocal current_chunk_content
            if current_chunk_content:
                chunks.append({
                    "content": current_chunk_content.strip(),
                    "metadata": {"breadcrumb_path": " > ".join(current_breadcrumbs)}
                })
                current_chunk_content = ""

        for unit in units:
            text = unit["content"]
            unit_len = len(text)
            
            # Update breadcrumb context for the active chunk
            if not current_chunk_content:
                current_breadcrumbs = unit["breadcrumbs"]

            # Merge Condition: Fits within limit
            if len(current_chunk_content) + unit_len <= self.chunk_size_limit:
                current_chunk_content += ("\n\n" if current_chunk_content else "") + text
            else:
                # Flush the current accumulator
                flush()
                
                # Split Condition: Single node exceeds limit
                if unit_len > self.chunk_size_limit:
                    if unit["is_atomic"]:
                        # Protection Measure: Never split tables or specific image descriptions
                        current_chunk_content = text
                        current_breadcrumbs = unit["breadcrumbs"]
                        flush()
                    else:
                        # Force-split large text nodes at sentence boundaries
                        sentences = re.split(r'(?<=[.!?]) +', text)
                        for sentence in sentences:
                            if len(current_chunk_content) + len(sentence) > self.chunk_size_limit:
                                flush()
                                current_breadcrumbs = unit["breadcrumbs"]
                            current_chunk_content += (" " if current_chunk_content else "") + sentence
                        flush()
                else:
                    # Node fits by itself, start a new accumulation
                    current_chunk_content = text
                    current_breadcrumbs = unit["breadcrumbs"]

        # Final flush for any remaining content
        flush()
        
        return chunks