import re
import tiktoken
import marko
from marko.block import Heading, Paragraph, List as MDList, Quote, FencedCode, HTMLBlock, CodeBlock
from marko.ext.gfm import gfm
from marko.md_renderer import MarkdownRenderer
from typing import List, Dict, Any, Tuple
from loguru import logger
from app.core.config import settings

class ChunkingService:
    def __init__(self):
        # Initialize marko with GFM for Table support
        self.md = marko.Markdown(extensions=['gfm'], renderer=MarkdownRenderer)
        
        # Initialize tokenizer (defaulting to cl100k_base for GPT-4/o1/etc)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to load cl100k_base encoding, falling back to gpt2: {e}")
            self.tokenizer = tiktoken.get_encoding("gpt2")
            
    def _count_tokens(self, text: str) -> int:
        """Helper to count tokens in a string."""
        if not text: return 0
        return len(self.tokenizer.encode(text))

    def _contains_image(self, node) -> bool:
        """Recursively check if a node contains an image."""
        # In marko, images are usually in Paragraph children as Inline elements
        if hasattr(node, 'children'):
            if isinstance(node.children, list):
                for child in node.children:
                    if type(child).__name__ == 'Image':
                        return True
                    if self._contains_image(child):
                        return True
            elif type(node.children).__name__ == 'Image':
                return True
        return False

    async def chunk_markdown(self, markdown_text: str, max_chunk_tokens: int) -> List[Dict[str, Any]]:
        """
        Chunks a markdown string into semantic parts using marko AST (DFS approach).
        """
        # 1. Parse into AST
        ast = self.md.parse(markdown_text)
        
        # 2. DFS Traversal to extract initial semantic units
        raw_units = []
        self._dfs_traverse(ast, header_stack=[], units_accumulator=raw_units)
        
        # 3. Merge descriptions with their preceding images/tables
        semantic_units = self._merge_contextual_descriptions(raw_units)
        
        # 4. Aggregate units into chunks
        return self._aggregate_units(semantic_units, max_chunk_tokens)

    def _dfs_traverse(self, node: Any, header_stack: List[str], units_accumulator: List[Dict]):
        """Recursively walks the AST, updating breadcrumbs and extracting leaf units."""
        
        # Update breadcrumbs if we hit a Heading
        if isinstance(node, Heading):
            level = node.level
            # Render heading to get text
            heading_md = self.md.render(node).strip()
            heading_text = heading_md.lstrip('#').strip()
            
            header_stack[:] = header_stack[:level-1]
            header_stack.append(heading_text)
            return

        # Identify leaf blocks
        is_table = type(node).__name__ == 'Table'
        is_leaf_block = isinstance(node, (Paragraph, MDList, Quote, FencedCode, CodeBlock, HTMLBlock)) or is_table

        if is_leaf_block:
            rendered_md = self.md.render(node)
            has_image = self._contains_image(node)
            has_table = is_table or ("<table" in rendered_md.lower())
            has_code = isinstance(node, (FencedCode, CodeBlock))
            
            # Check for atomic contextual descriptions
            is_contextual_desc = ("<IMAGE_CONTEXTUAL_DESCRIPTION>" in rendered_md or "<TABLE_CONTEXTUAL_DESCRIPTION>" in rendered_md)
            
            units_accumulator.append({
                "content": rendered_md,
                "tokens": self._count_tokens(rendered_md),
                "breadcrumbs": list(header_stack),
                "has_image": has_image,
                "has_table": has_table,
                "has_code": has_code,
                "is_atomic": is_table or has_code or is_contextual_desc or has_image
            })
            return

        # Continue DFS for children
        if hasattr(node, 'children') and isinstance(node.children, list):
            for child in node.children:
                self._dfs_traverse(child, header_stack, units_accumulator)

    def _merge_contextual_descriptions(self, units: List[Dict]) -> List[Dict]:
        """Second pass to merge images/tables with their descriptions."""
        merged = []
        i = 0
        while i < len(units):
            unit = units[i]
            
            can_have_desc = unit["has_image"] or unit["has_table"]
            
            if can_have_desc and i + 1 < len(units):
                next_unit = units[i+1]
                desc_tag = "<IMAGE_CONTEXTUAL_DESCRIPTION>" if unit["has_image"] else "<TABLE_CONTEXTUAL_DESCRIPTION>"
                
                if desc_tag in next_unit["content"]:
                    # Merge them!
                    unit["content"] += "\n" + next_unit["content"]
                    unit["tokens"] += next_unit["tokens"]
                    # Update flags
                    unit["has_image"] |= next_unit["has_image"]
                    unit["has_table"] |= next_unit["has_table"]
                    unit["has_code"] |= next_unit["has_code"]
                    unit["is_atomic"] = True
                    # Breadcrumbs are usually the same, but take the most specific one
                    if len(next_unit["breadcrumbs"]) > len(unit["breadcrumbs"]):
                        unit["breadcrumbs"] = next_unit["breadcrumbs"]
                    merged.append(unit)
                    i += 2
                    continue
            
            merged.append(unit)
            i += 1
        return merged

    def _aggregate_units(self, units: List[Dict], max_tokens: int) -> List[Dict[str, Any]]:
        """Merges small units and force-splits large ones."""
        chunks = []
        current_content = []
        current_tokens = 0
        current_metadata = {
            "breadcrumbs": [],
            "has_image": False,
            "has_table": False,
            "has_code": False
        }

        def flush():
            nonlocal current_content, current_tokens, current_metadata
            if current_content:
                content = "".join(current_content).strip()
                if content:
                    chunks.append({
                        "content": content,
                        "metadata": {
                            "breadcrumbs": current_metadata["breadcrumbs"],
                            "content_length": current_tokens,
                            "has_image": current_metadata["has_image"],
                            "has_table": current_metadata["has_table"],
                            "has_code": current_metadata["has_code"]
                        }
                    })
                current_content = []
                current_tokens = 0
                current_metadata = {
                    "breadcrumbs": [],
                    "has_image": False,
                    "has_table": False,
                    "has_code": False
                }

        for unit in units:
            u_tokens = unit["tokens"]
            u_md = unit["content"]
            u_meta = {
                "breadcrumbs": unit["breadcrumbs"],
                "has_image": unit["has_image"],
                "has_table": unit["has_table"],
                "has_code": unit["has_code"]
            }

            # Update breadcrumbs for the new chunk if it's empty
            if not current_content or len(u_meta["breadcrumbs"]) > len(current_metadata["breadcrumbs"]):
                current_metadata["breadcrumbs"] = u_meta["breadcrumbs"]

            # Check if it fits
            if current_tokens + u_tokens <= max_tokens:
                current_content.append(u_md)
                current_tokens += u_tokens
                current_metadata["has_image"] |= u_meta["has_image"]
                current_metadata["has_table"] |= u_meta["has_table"]
                current_metadata["has_code"] |= u_meta["has_code"]
            else:
                flush()
                
                # If single unit exceeds limit
                if u_tokens > max_tokens:
                    if unit["is_atomic"]:
                        # Keep atomic units together even if they exceed the limit
                        current_content = [u_md]
                        current_tokens = u_tokens
                        current_metadata.update(u_meta)
                        flush()
                    else:
                        # Split non-atomic large nodes (Paragraphs)
                        sentences = re.split(r'(?<=[.!?]) +', u_md)
                        for sentence in sentences:
                            s_tokens = self._count_tokens(sentence)
                            if current_tokens + s_tokens > max_tokens and current_content:
                                flush()
                                current_metadata["breadcrumbs"] = u_meta["breadcrumbs"]
                            
                            current_content.append(sentence)
                            current_tokens += s_tokens
                            current_metadata["has_image"] |= u_meta["has_image"]
                            current_metadata["has_table"] |= u_meta["has_table"]
                            current_metadata["has_code"] |= u_meta["has_code"]
                        flush()
                else:
                    # Fits as a new chunk
                    current_content = [u_md]
                    current_tokens = u_tokens
                    current_metadata.update(u_meta)

        flush()
        return chunks
