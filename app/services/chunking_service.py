import re
import tiktoken
import mistletoe
from mistletoe.block_token import Heading, Paragraph, List as MDList, ListItem, Table, CodeFence, Quote, HTMLBlock
from mistletoe.markdown_renderer import MarkdownRenderer
from typing import List as typingList, Dict, Any
from loguru import logger

class ChunkingService:
    def __init__(self):
        # Initialize tokenizer
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to load cl100k_base encoding, falling back to gpt2: {e}")
            self.tokenizer = tiktoken.get_encoding("gpt2")
            
    def _count_tokens(self, text: str) -> int:
        """Helper to count tokens in a string."""
        if not text: return 0
        return len(self.tokenizer.encode(text))

    def _is_contextual_description(self, text: str) -> bool:
        """Checks if the text contains a contextual description tag."""
        return "<IMAGE_CONTEXTUAL_DESCRIPTION>" in text or "<TABLE_CONTEXTUAL_DESCRIPTION>" in text

    def _contains_image(self, node) -> bool:
        """Recursively check if a node contains an image span token."""
        from mistletoe.span_token import Image
        if isinstance(node, Image):
            return True
        if hasattr(node, 'children') and isinstance(node.children, (list, tuple)):
            for child in node.children:
                if self._contains_image(child):
                    return True
        return False

    async def chunk_markdown(self, markdown_text: str, max_chunk_tokens: int) -> typingList[Dict[str, Any]]:
        """
        Chunks a markdown string into semantic parts using mistletoe AST (DFS + Pruning).
        """
        try:
            # Use MarkdownRenderer as a context manager to ensure correct setup/teardown
            # We wrap it in a try-except to handle the mistletoe bug with multiple initializations
            try:
                renderer = MarkdownRenderer()
            except ValueError:
                # If Footnote removal fails, we try to use a dummy renderer or a workaround
                # Actually, in most cases, we can just use the class directly if needed
                # but let's try to be as standard as possible.
                renderer = MarkdownRenderer()

            with renderer:
                self.renderer = renderer
                # 1. Parse into AST
                doc = mistletoe.Document(markdown_text)
                
                # 2. Recursive DFS with AST Pruning (aggregation at each level)
                chunks = self._dfs_chunk(doc, header_stack=[], limit=max_chunk_tokens)
                
                # 3. Final cleanup of chunks (formatting for output)
                return [
                    {
                        "content": ch["content"],
                        "metadata": ch["metadata"]
                    }
                    for ch in chunks
                ]
        except Exception as e:
            logger.error(f"Error during mistletoe chunking: {e}")
            # Fallback to simple splitting if AST parsing fails
            return [{"content": markdown_text, "metadata": {"breadcrumbs": [], "error": str(e)}}]

    def _dfs_chunk(self, node: Any, header_stack: typingList[str], limit: int) -> typingList[Dict[str, Any]]:
        """
        Recursively walks the AST, returning a list of chunks for the given node.
        Implements AST Pruning by aggregating siblings before returning.
        """
        
        # A. Handle Headings (Metadata update)
        if isinstance(node, Heading):
            level = node.level
            # Render heading to get plain-ish text
            heading_md = self.renderer.render(node).strip()
            heading_text = heading_md.lstrip('#').strip()
            
            # Update breadcrumbs (pop deeper/same levels)
            header_stack[:] = header_stack[:level-1]
            header_stack.append(heading_text)
            return [] # Headings are consumed into metadata

        # B. Handle Leaf Blocks
        is_container = isinstance(node, (mistletoe.block_token.Document, MDList, ListItem, Quote))
        
        if not is_container:
            content = self.renderer.render(node).strip()
            if not content:
                return []
            
            tokens = self._count_tokens(content)
            has_image = self._contains_image(node)
            is_atomic = isinstance(node, (Table, CodeFence)) or has_image or self._is_contextual_description(content)
            
            if tokens > limit and not is_atomic:
                # Split large paragraphs
                return self._split_text(content, header_stack, limit)
            else:
                return [{
                    "content": content,
                    "tokens": tokens,
                    "metadata": {
                        "breadcrumbs": list(header_stack),
                        "type": type(node).__name__,
                        "has_image": has_image,
                        "has_table": isinstance(node, Table) or "<table" in content.lower()
                    }
                }]

        # C. Handle Container Blocks
        child_chunks = []
        if hasattr(node, 'children') and isinstance(node.children, (list, tuple)):
            for child in node.children:
                child_chunks.extend(self._dfs_chunk(child, header_stack, limit))
        
        # D. AST Pruning: Aggregate siblings under this parent
        return self._aggregate_chunks(child_chunks, limit)

    def _aggregate_chunks(self, chunks: typingList[Dict], limit: int) -> typingList[Dict]:
        """
        Aggregates adjacent chunks if they fit within the limit.
        Also handles mandatory binding of contextual descriptions to preceding units.
        """
        if not chunks:
            return []
        
        aggregated = []
        current = None
        
        for next_ch in chunks:
            if current is None:
                current = next_ch
                continue
            
            # Check for atomic contextual description binding
            is_desc = self._is_contextual_description(next_ch["content"])
            
            # If next is a description, it MUST be merged with the current unit
            # Or if they fit together
            if is_desc or (current["tokens"] + next_ch["tokens"] <= limit):
                joiner = "\n" if is_desc else "\n\n"
                current["content"] += joiner + next_ch["content"]
                current["tokens"] = self._count_tokens(current["content"])
                
                # Merge basic metadata flags
                current["metadata"]["has_image"] = current["metadata"].get("has_image", False) or next_ch["metadata"].get("has_image", False)
                current["metadata"]["has_table"] = current["metadata"].get("has_table", False) or next_ch["metadata"].get("has_table", False)
                
                # Breadcrumbs: use the one with more depth if different
                if len(next_ch["metadata"]["breadcrumbs"]) > len(current["metadata"]["breadcrumbs"]):
                    current["metadata"]["breadcrumbs"] = next_ch["metadata"]["breadcrumbs"]
            else:
                aggregated.append(current)
                current = next_ch
                
        if current:
            aggregated.append(current)
            
        return aggregated

    def _split_text(self, text: str, breadcrumbs: typingList[str], limit: int) -> typingList[Dict]:
        """Splits a large text block into smaller chunks at sentence boundaries."""
        # Split by sentences, handling spaces or newlines after punctuation
        sentences = re.split(r'(?<=[.!?])[\s\n]+', text)
        chunks = []
        current_content = []
        current_tokens = 0
        
        for sentence in sentences:
            s_tokens = self._count_tokens(sentence)
            
            if current_tokens + s_tokens > limit and current_content:
                content = " ".join(current_content).strip()
                chunks.append({
                    "content": content,
                    "tokens": current_tokens,
                    "metadata": {
                        "breadcrumbs": list(breadcrumbs),
                        "type": "ParagraphSplitted"
                    }
                })
                current_content = []
                current_tokens = 0
            
            current_content.append(sentence)
            current_tokens += s_tokens
            
        if current_content:
            content = " ".join(current_content).strip()
            chunks.append({
                "content": content,
                "tokens": current_tokens,
                "metadata": {
                    "breadcrumbs": list(breadcrumbs),
                    "type": "ParagraphSplitted"
                }
            })
            
        return chunks
