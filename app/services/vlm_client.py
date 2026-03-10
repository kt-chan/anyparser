import base64
import asyncio
from pathlib import Path
from openai import AsyncOpenAI, RateLimitError
from app.core.config import settings
from loguru import logger
import json_repair


class VLMClient:
    _semaphore = asyncio.Semaphore(5)

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.VLM_API_KEY, base_url=settings.VLM_HOST_PATH
        )
        self.model = settings.VLM_MODEL_NAME
        self.max_retries = 3
        self.retry_delay = 2  # seconds

    async def analyze_image(
        self, 
        image_path: Path, 
        document_summary: str,
        heading_path: str,
        section_summary: str,
        surrounding_text: str
    ) -> dict:
        """
        Analyzes an image using the VLM with recursive context stack.
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found at {image_path}")

        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        system_prompt = (
            "You are a document analysis assistant. Analyze the provided image based on its global and local document context. "
            "Return a JSON object with two fields: 'title' (a 10-word technical alt-text) and 'analysis' "
            "(a detailed technical description explaining how the image supports the document context)."
        )

        # Updated VLM Prompt Template per requirements
        user_prompt = (
            f"**Document Purpose:** {document_summary}\n"
            f"**Document Catalog:** {heading_path}\n"
            f"**Section Summary:** {section_summary}\n"
            f"**Immediate Text:** {surrounding_text[:500]}\n\n"
            "**Task:** Analyze the image and provide a descriptive alt-text and a detailed contextual description "
            "that explains how this image supports the section summary above."
        )
        
        messages_content = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"},
                    },
                ],
            },
        ]

        for attempt in range(self.max_retries + 1):
            try:
                async with self._semaphore:
                    logger.info(f"VLM Request - Model: {self.model} for {image_path.name}")
                    response = await self.client.chat.completions.create(
                        model=self.model, messages=messages_content, temperature=0.2
                    )

                content = response.choices[0].message.content
                try:
                    result = json_repair.loads(content)
                    if (
                        isinstance(result, dict)
                        and "title" in result
                        and "analysis" in result
                    ):
                        return result
                    else:
                        logger.warning(
                            f"VLM returned unexpected JSON structure: {content}"
                        )
                        raise ValueError("Invalid JSON structure from VLM")
                except Exception as e:
                    logger.error(
                        f"Failed to parse VLM response as JSON: {content}. Error: {e}"
                    )
                    raise e

            except RateLimitError as e:
                if attempt < self.max_retries:
                    logger.warning(
                        f"Rate limit hit for {image_path}. Retrying in {self.retry_delay}s..."
                    )
                    await asyncio.sleep(self.retry_delay)
                    continue
                else:
                    raise e
            except Exception as e:
                logger.error(f"VLM analysis failed for {image_path}: {e}")
                raise e
