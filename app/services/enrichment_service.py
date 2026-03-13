import re
import asyncio
import hashlib
from typing import Optional, List
from pathlib import Path
from loguru import logger
from app.services.vlm_client import VLMClient
from app.services.llm_client import LLMClient
from app.utils.markdown_parser import MarkdownParser, SemanticSection
from app.core.config import settings
import os

# Setup logger for this service
log_file = Path(settings.LOGS_DIR) / "vlm_enrichment_service.log"
os.makedirs(settings.LOGS_DIR, exist_ok=True)
logger.add(log_file, rotation="500 MB", level="INFO", filter=lambda record: record["extra"].get("service") == "vlm_enrichment")
vlm_logger = logger.bind(service="vlm_enrichment")

class VLMEnrichmentService:
    def __init__(self, content_batch_size: int = 2000):
        self.vlm_client = VLMClient()
        self.llm_client = LLMClient()
        self.parser = MarkdownParser()
        self.image_pattern = re.compile(r"!\[.*?\]\(([^)]+)\)")
        self.table_pattern = re.compile(r"(<table>.*?</table>|^\s*\|.*\|(?:\n\s*\|.*\|)+)", re.DOTALL | re.MULTILINE)
        self.content_batch_size = content_batch_size
        self.token_to_char_ratio = 4

    async def enrich_markdown(self, md_file_path: Path, content_batch_size: Optional[int] = None):
        md_file_path = Path(md_file_path)
        if not md_file_path.exists():
            vlm_logger.error(f"Markdown file not found: {md_file_path}")
            return

        batch_size = content_batch_size or self.content_batch_size
        batch_size_chars = batch_size * self.token_to_char_ratio

        with open(md_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        vlm_logger.info(f"Restoring header hierarchy for {md_file_path}")
        content = await self._restore_header_hierarchy(content)

        vlm_logger.info(f"Parsing structural tree for {md_file_path}")
        root = self.parser.parse(content)

        vlm_logger.info(f"Merging small subsections for {md_file_path}")
        self._merge_sections(root, batch_size_chars)

        if settings.ENABLE_LLM_SUMMARIZATION:
            vlm_logger.info(f"Starting bottom-up summarization for {md_file_path}")
            await self._summarize_recursive(root)
        else:
            vlm_logger.info(f"LLM summarization disabled, using raw content for {md_file_path}")
            self._fallback_to_raw_content(root)
        
        vlm_logger.info(f"Starting context-aware VLM/LLM enrichment for {md_file_path}")
        # Process images/tables and update node.own_content directly
        await self._enrich_sections_recursive(root, md_file_path.parent)
        
        # Reconstruct the full content from updated tree if needed for saving to file
        def reconstruct_content(node):
            full = node.own_content
            for child in node.children:
                full += reconstruct_content(child)
            return full
        
        enriched_content = reconstruct_content(root)
        
        with open(md_file_path, "w", encoding="utf-8") as f:
            f.write(enriched_content)
        
        vlm_logger.info(f"Successfully enriched {md_file_path}")
        return root

    def _merge_sections(self, section: SemanticSection, max_chars: int):
        """
        Recursively merges sub-sections to reduce LLM calls while maintaining document order.
        """
        for child in section.children:
            self._merge_sections(child, max_chars)

        if not section.children:
            return

        merged_children = []
        current_receiver = section
        
        pending = list(section.children)
        section.children = []
        
        while pending:
            child = pending.pop(0)
            if len(current_receiver.own_content) + len(child.own_content) < max_chars:
                vlm_logger.debug(f"Merging section '{child.title}' into '{current_receiver.title}'")
                current_receiver.own_content += child.own_content
                if child.children:
                    pending[0:0] = child.children
            else:
                merged_children.append(child)
                current_receiver = child
                
        section.children = merged_children

    async def _summarize_recursive(self, section: SemanticSection):
        child_tasks = []
        if section.children:
            child_tasks = [self._summarize_recursive(child) for child in section.children]

        async def get_own_summary():
            if section.own_content.strip():
                section.own_summary = await self.llm_client.summarize(section.own_content)
            else:
                section.own_summary = ""

        await asyncio.gather(get_own_summary(), *child_tasks)

        if not section.children:
            section.context_summary = section.own_summary
            return

        children_summaries_list = [f"- {c.title}: {c.context_summary}" for c in section.children]
        children_summaries = "\n".join(children_summaries_list)
        
        section.context_summary = await self.llm_client.summarize(section.own_content, children_summaries)

    def _fallback_to_raw_content(self, section: SemanticSection):
        """
        Populates own_summary and context_summary with raw content snippets.
        """
        section.own_summary = section.own_content[:1000].strip()
        
        for child in section.children:
            self._fallback_to_raw_content(child)
            
        if not section.children:
            section.context_summary = section.own_summary
        else:
            child_info = ", ".join([c.title for c in section.children])
            section.context_summary = f"{section.own_summary}\nSub-sections: {child_info}"

    async def _enrich_sections_recursive(self, section: SemanticSection, base_dir: Path):
        """
        Processes images and tables in this section and its children.
        """
        document_summary = section.context_summary

        async def process_node(node: SemanticSection, current_path: list[str]):
            new_path = current_path + [node.title] if node.title != "Root" else current_path
            heading_path = " > ".join(new_path)
            
            tasks = []
            
            # 1. Gather Image Tasks
            image_matches = list(self.image_pattern.finditer(node.own_content))
            for match in image_matches:
                image_rel_path = match.group(1)
                image_abs_path = base_dir / image_rel_path
                
                start_ctx = max(0, match.start() - 250)
                end_ctx = min(len(node.own_content), match.end() + 250)
                surrounding_text = node.own_content[start_ctx:end_ctx]
                
                task = self.process_image(
                    image_abs_path,
                    document_summary,
                    heading_path,
                    node.own_summary,
                    surrounding_text,
                    match.group(0),
                    match.start(),
                    match.end()
                )
                tasks.append(task)

            # 2. Gather Table Tasks
            table_matches = list(self.table_pattern.finditer(node.own_content))
            for match in table_matches:
                table_content = match.group(0)
                
                start_ctx = max(0, match.start() - 250)
                end_ctx = min(len(node.own_content), match.end() + 250)
                surrounding_text = node.own_content[start_ctx:end_ctx]
                
                task = self.process_table(
                    table_content,
                    document_summary,
                    heading_path,
                    node.own_summary,
                    surrounding_text,
                    match.start(),
                    match.end()
                )
                tasks.append(task)
            
            if tasks:
                results = await asyncio.gather(*tasks)
                # Results are tuples of (original_tag, enriched_tag, start_idx, end_idx)
                # Filter out None results (failures)
                valid_results = [r for r in results if r[1] is not None]
                # Sort by start_idx descending to replace in-place without shifting indices
                valid_results.sort(key=lambda x: x[2], reverse=True)
                
                new_own_content = node.own_content
                for original_tag, enriched_tag, start_idx, end_idx in valid_results:
                    new_own_content = new_own_content[:start_idx] + enriched_tag + new_own_content[end_idx:]
                node.own_content = new_own_content

            # Process children
            if node.children:
                await asyncio.gather(*[process_node(child, new_path) for child in node.children])

        await process_node(section, [])

    async def process_image(self, image_path, doc_sum, path, sec_sum, text, tag, start, end):
        try:
            result = await self.vlm_client.analyze_image(
                image_path=image_path,
                document_summary=doc_sum,
                heading_path=path,
                section_summary=sec_sum,
                surrounding_text=text
            )
            title = result.get("title", "Image")
            analysis = result.get("analysis", "No description available.")
            
            match = self.image_pattern.match(tag)
            rel_path = match.group(1) if match else ""
            
            enriched_tag = f"![{title}]({rel_path})\n\n<IMAGE_CONTEXTUAL_DESCRIPTION>{' '.join(analysis.split())}</IMAGE_CONTEXTUAL_DESCRIPTION>\n"
            return tag, enriched_tag, start, end
        except Exception as e:
            vlm_logger.error(f"Error processing image {image_path}: {e}")
            return tag, None, start, end

    async def process_table(self, table_content, doc_sum, path, sec_sum, text, start, end):
        try:
            analysis = await self.llm_client.analyze_table(
                table_content=table_content,
                document_summary=doc_sum,
                heading_path=path,
                section_summary=sec_sum,
                surrounding_text=text
            )
            enriched_tag = f"{table_content}\n\n<TABLE_CONTEXTUAL_DESCRIPTION>{' '.join(analysis.split())}</TABLE_CONTEXTUAL_DESCRIPTION>\n"
            return table_content, enriched_tag, start, end
        except Exception as e:
            vlm_logger.error(f"Error processing table: {e}")
            return table_content, None, start, end

    async def _restore_header_hierarchy(self, content: str) -> str:
        """
        Identifies potential header lines and uses LLM to restore correct nesting levels.
        """
        lines = content.splitlines()
        potential_headers = []
        header_indices = []

        # Heuristic to find potential headers
        for i, line in enumerate(lines):

            if not line.strip():
                continue
            
            # 1. Already a header
            if line.startswith("#"):
                potential_headers.append(line)
                header_indices.append(i)
                continue
            
            # 2. Numbering pattern (e.g., 1.1, 2 - , A.)
            if re.match(r"^\d+(\.\d+)*\s*[-.]\s+", line) or re.match(r"^[A-Z]\.\s+", line):
                potential_headers.append(line)
                header_indices.append(i)
                continue
            
            # 3. Short line ending with page number (common in MinerU TOC/headers)
            if len(line) < 100 and re.match(r"^.*?\s+\d+$", line):
                potential_headers.append(line)
                header_indices.append(i)
                continue

        if not potential_headers:
            return content

        # Call LLM to restore hierarchy
        try:
            corrected_headers = await self.llm_client.restore_headers(potential_headers)
            
            # Map back to original lines
            new_lines = list(lines)
            for i, corrected in enumerate(corrected_headers):
                if i < len(header_indices):
                    idx = header_indices[i]
                    # Ensure the corrected text is what the LLM returned
                    # Remove all leading '#' characters from the text
                    stripped_text = corrected.corrected_text.lstrip('#')
                    # Prepend '#' repeated 'level' times
                    corrected.corrected_text = '#' * corrected.level + stripped_text
                    new_lines[idx] = corrected.corrected_text
            
            return "\n".join(new_lines)
        except Exception as e:
            vlm_logger.error(f"Failed to restore header hierarchy: {e}")
            return content
