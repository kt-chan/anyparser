import re
import asyncio
from pathlib import Path
from loguru import logger
from app.services.vlm_client import VLMClient
from app.core.config import settings
import os

# Setup logger for this service
log_file = Path(settings.LOGS_DIR) / "vlm_enrichment_service.log"
os.makedirs(settings.LOGS_DIR, exist_ok=True)
logger.add(log_file, rotation="500 MB", level="INFO", filter=lambda record: record["extra"].get("service") == "vlm_enrichment")
vlm_logger = logger.bind(service="vlm_enrichment")

class VLMEnrichmentService:
    def __init__(self):
        self.client = VLMClient()
        self.semaphore = asyncio.Semaphore(5)
        # Regex to find empty image tags: ![](path)
        self.image_pattern = re.compile(r"!\[\]\(([^)]+)\)")

    async def enrich_markdown(self, md_file_path: Path):
        """
        Processes a markdown file, finds images, analyzes them, and updates the file.
        """
        md_file_path = Path(md_file_path)
        if not md_file_path.exists():
            vlm_logger.error(f"Markdown file not found: {md_file_path}")
            return

        with open(md_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        matches = list(self.image_pattern.finditer(content))
        if not matches:
            vlm_logger.info(f"No empty image tags found in {md_file_path}")
            return

        vlm_logger.info(f"Found {len(matches)} images to enrich in {md_file_path}")

        tasks = []
        for match in matches:
            image_rel_path = match.group(1)
            # Ensure path handling works for images in subfolders
            image_abs_path = md_file_path.parent / image_rel_path
            
            # Extract up to 500 characters of context before and after
            start_ctx = max(0, match.start() - 500)
            end_ctx = min(len(content), match.end() + 500)
            context = content[start_ctx:end_ctx]
            
            tasks.append(self.process_image(image_abs_path, context, match.group(0)))

        # Process images in parallel with semaphore limit
        results = await asyncio.gather(*tasks)

        # Replace tags in reverse order to maintain string indices
        new_content = content
        for i in range(len(matches) - 1, -1, -1):
            match = matches[i]
            original_tag, enriched_content = results[i]
            
            if enriched_content:
                new_content = new_content[:match.start()] + enriched_content + new_content[match.end():]
            else:
                vlm_logger.warning(f"Skipping enrichment for {match.group(1)} due to previous errors")

        with open(md_file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        vlm_logger.info(f"Successfully enriched {md_file_path}")

    async def process_image(self, image_path: Path, context: str, original_tag: str):
        """
        Analyzes a single image and returns the enriched markdown block.
        """
        async with self.semaphore:
            try:
                # Get path from original tag to preserve it
                match = self.image_pattern.match(original_tag)
                if not match:
                    return original_tag, None
                
                rel_path = match.group(1)
                
                # Call VLM Client
                result = await self.client.analyze_image(image_path, context)
                title = result.get("title", "Image")
                analysis = result.get("analysis", "No description available.")
                
                # Transform: ![title](path) followed by blockquote
                enriched_tag = f"![{title}]({rel_path})\n\n> **Contextual Description:** {analysis}"
                return original_tag, enriched_tag
                
            except Exception as e:
                vlm_logger.error(f"Error processing image {image_path}: {e}")
                return original_tag, None
