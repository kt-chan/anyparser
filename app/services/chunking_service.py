import base64
import uuid
import re
import shutil
import mistletoe
import tiktoken
from mistletoe.block_token import Table, Paragraph, Heading, CodeFence, Quote, List, ListItem, HtmlBlock
from mistletoe.span_token import Image
from mistletoe.markdown_renderer import MarkdownRenderer
from pathlib import Path
from typing import List, Dict, Any, Tuple
from loguru import logger
from app.services.mineru_client import MinerUWrapper
from app.services.enrichment_service import VLMEnrichmentService
from app.core.config import settings

class ChunkingService:
    def __init__(self):
        self.mineru_client = MinerUWrapper()
        self.vlm_enrichment_service = VLMEnrichmentService()
        self.renderer = MarkdownRenderer()
        # Initialize tokenizer (defaulting to cl100k_base for GPT-4/o1/etc)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to load cl100k_base encoding, falling back to gpt2: {e}")
            self.tokenizer = tiktoken.get_encoding("gpt2")
            
        # Pattern to capture enriched images: ![title](rel_path)\n\n> **Contextual Description:** analysis
        self.img_pattern = re.compile(r"!\[(.*?)\]\((.*?)\)\n\n> \*\*Contextual Description:\*\* (.*?)(?=\n\n|\Z)", re.DOTALL)

    def _count_tokens(self, text: str) -> int:
        """Helper to count tokens in a string."""
        if not text: return 0
        return len(self.tokenizer.encode(text))

    def _contains_image(self, node) -> bool:
        """Recursively check if a node contains an Image span token."""
        if isinstance(node, Paragraph):
            return any(isinstance(c, Image) for c in node.children)
        if hasattr(node, 'children') and node.children:
            return any(self._contains_image(c) for c in node.children)
        return False

    async def chunk_markdown(self, markdown_text: str, max_chunk_tokens: int) -> List[str]:
        """
        Chunks a markdown string into semantic parts using mistletoe AST.
        Unit: Tokens.
        No overlapping.
        Atomic protection for Tables, Code blocks, and Images with descriptions.
        """
        # 0. Normalize line breaks
        markdown_text = markdown_text.replace('\r\n', '\n').replace('\r', '\n')

        # 1. Parse into AST
        doc = mistletoe.Document(markdown_text)
        
        # 2. Pre-process nodes to merge Images/Tables with their Contextual Descriptions
        final_nodes: List[Tuple[str, str, int]] = [] # (type, content, tokens)
        i = 0
        nodes = doc.children
        while i < len(nodes):
            node = nodes[i]
            node_md = self.renderer.render(node)
            
            # Check if this node is an image or a table
            is_image_node = self._contains_image(node)
            is_table_node = isinstance(node, (Table, HtmlBlock)) and ("<table" in node_md.lower() or "|" in node_md)
            
            if is_image_node or is_table_node:
                # Look ahead for a Quote with description, skipping blank lines
                j = i + 1
                found_desc = False
                desc_tag = "<IMAGE_CONTEXTUAL_DESCRIPTION>" if is_image_node else "<TABLE_CONTEXTUAL_DESCRIPTION>"
                
                while j < len(nodes):
                    next_node = nodes[j]
                    if isinstance(next_node, mistletoe.markdown_renderer.BlankLine):
                        j += 1
                        continue
                    next_node_md = self.renderer.render(next_node)
                    if isinstance(next_node, Quote) and desc_tag in next_node_md:
                        # Found it! Merge everything from i to j into a single atomic block
                        merged_md = ""
                        for k in range(i, j + 1):
                            merged_md += self.renderer.render(nodes[k])
                        final_nodes.append(("atomic", merged_md, self._count_tokens(merged_md)))
                        i = j + 1
                        found_desc = True
                    break
                
                if found_desc:
                    continue

            # Standard atomic blocks
            is_atomic = isinstance(node, (Table, CodeFence))
            node_type = "atomic" if is_atomic else "node"
            final_nodes.append((node_type, node_md, self._count_tokens(node_md)))
            i += 1

        # 3. Buffer management
        chunks = []
        current_batch = []
        current_size = 0

        for n_type, n_md, n_tokens in final_nodes:
            # Handle Large Paragraphs (Splitting logic)
            if n_type == "node" and n_tokens > max_chunk_tokens:
                # Flush pending
                if current_batch:
                    chunks.append("".join(current_batch))
                    current_batch, current_size = [], 0
                
                # Split large text by sentences
                sentences = re.split(r'(?<=[.!?]) +', n_md)
                for sentence in sentences:
                    s_tokens = self._count_tokens(sentence)
                    if current_size + s_tokens > max_chunk_tokens:
                        if current_batch:
                            chunks.append("".join(current_batch))
                        current_batch = [sentence]
                        current_size = s_tokens
                    else:
                        current_batch.append(sentence)
                        current_size += s_tokens
                continue

            # Standard Buffer Management
            if current_size + n_tokens > max_chunk_tokens and current_size > 0:
                # Flush current chunk
                chunks.append("".join(current_batch))
                current_batch = [n_md]
                current_size = n_tokens
            else:
                current_batch.append(n_md)
                current_size += n_tokens

        if current_batch:
            chunks.append("".join(current_batch))
            
        return [c.strip() for c in chunks if c.strip()]

    async def process_pdf_to_chunks(self, pdf_base64: str) -> List[Dict[str, Any]]:
        """
        Parse a PDF file from base64 and return multi-modal chunks.
        """
        job_id = str(uuid.uuid4())
        # Create job-specific temp directory
        job_dir = Path(settings.TEMP_DIR) / f"job_{job_id}"
        job_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = job_dir / "input.pdf"

        try:
            # Decode and save PDF
            logger.info(f"Decoding PDF for job {job_id}")
            pdf_bytes = base64.b64decode(pdf_base64)
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)

            # 1. Process with MinerU
            logger.info(f"Processing PDF with MinerU for job {job_id}")
            output_dir = await self.mineru_client.process_pdf(pdf_path)
            
            # 2. Enrich with VLM
            md_files = list(output_dir.rglob("*.md"))
            if not md_files:
                logger.error("No markdown files generated by MinerU")
                return [{"type": "error", "content": "No markdown output generated by MinerU"}]
            
            md_file = md_files[0]
            logger.info(f"Enriching markdown {md_file.name} for job {job_id}")
            root_section = await self.vlm_enrichment_service.enrich_markdown(md_file)

            # 3. Extract multi-modal chunks
            chunks = []
            self._collect_chunks(root_section, md_file.parent, chunks)
            
            logger.info(f"Successfully chunked PDF into {len(chunks)} chunks for job {job_id}")
            return chunks

        except Exception as e:
            logger.error(f"Error in smart_chunking: {e}")
            return [{"type": "error", "content": f"Internal server error: {str(e)}"}]
        finally:
            # Cleanup job directory
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
            except:
                pass

    def _collect_chunks(self, section, base_path: Path, chunks: list):
        content = section.own_content
        # Split content by images, but keep the captured groups
        parts = re.split(r"(!\[.*?\]\(.*?\)\n\n> \*\*Contextual Description:\*\* .*?)(?=\n\n|\Z)", content, flags=re.DOTALL)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Try to match the image pattern
            img_match = self.img_pattern.match(part)
            if img_match:
                title, rel_path, analysis = img_match.groups()
                img_abs_path = base_path / rel_path
                
                if img_abs_path.exists():
                    with open(img_abs_path, "rb") as img_f:
                        img_b64 = base64.b64encode(img_f.read()).decode("utf-8")
                    chunks.append({
                        "type": "image",
                        "data": img_b64,
                        "format": "png",
                        "metadata": {
                            "title": title,
                            "analysis": analysis,
                            "section": section.title
                        }
                    })
                else:
                    logger.warning(f"Image file not found: {img_abs_path}")
                    chunks.append({"type": "text", "content": f"[Image not found: {title}]"})
            else:
                # It's a text chunk
                chunks.append({
                    "type": "text",
                    "content": part,
                    "metadata": {
                        "section": section.title,
                        "level": section.level
                    }
                })

        for child in section.children:
            self._collect_chunks(child, base_path, chunks)
