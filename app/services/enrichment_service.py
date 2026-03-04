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
        # Limit concurrent remote calls (LLM + VLM)
        self.semaphore = asyncio.Semaphore(5)
        self.image_pattern = re.compile(r"!\[.*?\]\(([^)]+)\)")
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

        vlm_logger.info(f"Parsing structural tree for {md_file_path}")
        root = self.parser.parse(content)

        vlm_logger.info(f"Merging small subsections for {md_file_path} (batch size: {batch_size} tokens)")
        self._merge_sections(root, batch_size_chars)

        vlm_logger.info(f"Starting bottom-up summarization for {md_file_path}")
        await self._summarize_recursive(root)
        
        vlm_logger.info(f"Starting context-aware VLM enrichment for {md_file_path}")
        enriched_content = await self._enrich_sections_recursive(root, content, md_file_path.parent)
        
        with open(md_file_path, "w", encoding="utf-8") as f:
            f.write(enriched_content)
        
        vlm_logger.info(f"Successfully enriched {md_file_path}")

    def _merge_sections(self, section: SemanticSection, max_chars: int):
        """
        Recursively merges sub-sections to reduce LLM calls while maintaining document order.
        Sub-sections are merged into their parent or preceding sibling as long as the 
        combined content stays within max_chars.
        """
        # 1. Bottom-up: process children first
        for child in section.children:
            self._merge_sections(child, max_chars)

        if not section.children:
            return

        # 2. Greedy merge siblings into parent or each other
        merged_children = []
        current_receiver = section
        
        # Use a list for the pending sections to process at this level
        pending = list(section.children)
        section.children = [] # Reset, will be rebuilt with unmerged children
        
        while pending:
            child = pending.pop(0)
            
            # Check if we can merge 'child' into 'current_receiver'
            if len(current_receiver.own_content) + len(child.own_content) < max_chars:
                vlm_logger.debug(f"Merging section '{child.title}' into '{current_receiver.title}'")
                current_receiver.own_content += child.own_content
                
                # If we merged into a receiver, its new children are the child's children
                # These must be processed NEXT at this level to maintain order
                if child.children:
                    pending[0:0] = child.children
            else:
                # Cannot merge child into current_receiver.
                # child stays as a distinct section and becomes the new receiver.
                merged_children.append(child)
                current_receiver = child
                
        section.children = merged_children

    async def _summarize_recursive(self, section: SemanticSection):
        # 1. Start children summarization in parallel
        child_tasks = []
        if section.children:
            child_tasks = [self._summarize_recursive(child) for child in section.children]

        # 2. Start own summary calculation in parallel
        async def get_own_summary():
            if section.own_content.strip():
                async with self.semaphore:
                    section.own_summary = await self.llm_client.summarize(section.own_content)
            else:
                section.own_summary = ""

        # 3. Wait for own summary AND all children to finish their full recursive summarization
        # This includes children's context summaries
        await asyncio.gather(get_own_summary(), *child_tasks)

        # 4. Final aggregation: context_summary depends on children summaries being ready
        if not section.children:
            section.context_summary = section.own_summary
            return

        # At this point, all children have finished _summarize_recursive, 
        # so their context_summary fields are populated.
        children_summaries_list = [f"- {c.title}: {c.context_summary}" for c in section.children]
        children_summaries = "\n".join(children_summaries_list)
        
        async with self.semaphore:
            section.context_summary = await self.llm_client.summarize(section.own_content, children_summaries)

    async def _enrich_sections_recursive(
        self, 
        section: SemanticSection, 
        full_content: str, 
        base_dir: Path
    ) -> str:
        image_tasks = []
        document_summary = section.context_summary

        def collect_image_tasks(node: SemanticSection, current_path: list[str]):
            new_path = current_path + [node.title] if node.title != "Root" else current_path
            
            # Find all image matches in this section's own content
            matches = list(self.image_pattern.finditer(node.own_content))
            for match in matches:
                image_rel_path = match.group(1)
                image_abs_path = base_dir / image_rel_path
                
                heading_path = " > ".join(new_path)
                
                # Context stack: surrounding 500 characters (250 before, 250 after)
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
                    node.start_index + match.start(),
                    node.start_index + match.end()
                )
                image_tasks.append(task)
            
            for child in node.children:
                collect_image_tasks(child, new_path)

        collect_image_tasks(section, [])
        
        if not image_tasks:
            return full_content

        vlm_logger.info(f"Processing {len(image_tasks)} images with context stack")
        results = await asyncio.gather(*image_tasks)
        
        results.sort(key=lambda x: x[2], reverse=True)
        
        new_content = full_content
        for original_tag, enriched_tag, start_idx, end_idx in results:
            if enriched_tag:
                new_content = new_content[:start_idx] + enriched_tag + new_content[end_idx:]
                
        return new_content

    async def process_image(self, *args, **kwargs):
        # We need original_tag and indices for the result
        original_tag = args[5]
        start_idx = args[6]
        end_idx = args[7]
        
        async with self.semaphore:
            try:
                # Call VLM Client with context stack
                # args: image_path, doc_sum, path, sec_sum, text, tag, start, end
                result = await self.vlm_client.analyze_image(
                    image_path=args[0],
                    document_summary=args[1],
                    heading_path=args[2],
                    section_summary=args[3],
                    surrounding_text=args[4]
                )
                
                title = result.get("title", "Image")
                analysis = result.get("analysis", "No description available.")
                
                # Extract original relative path to preserve it
                match = self.image_pattern.match(original_tag)
                rel_path = match.group(1) if match else ""
                
                enriched_tag = f"![{title}]({rel_path})\n\n> **Contextual Description:** {analysis}"
                return original_tag, enriched_tag, start_idx, end_idx
                
            except Exception as e:
                vlm_logger.error(f"Error processing image {args[0]}: {e}")
                return original_tag, None, start_idx, end_idx
