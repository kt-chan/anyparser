import base64
import asyncio
from pathlib import Path
from openai import AsyncOpenAI, RateLimitError
from app.core.config import settings
from loguru import logger
import json_repair


class VLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.VLM_API_KEY, base_url=settings.VLM_HOST_PATH
        )
        self.model = settings.VLM_MODEL_NAME
        self.max_retries = 3
        self.retry_delay = 2  # seconds

    async def analyze_image(self, image_path: Path, context_text: str) -> dict:
        """
        Analyzes an image using the VLM with surrounding text context.
        Returns a dict with 'title' and 'analysis'.
        Includes retry logic for RateLimitError (429).
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found at {image_path}")

        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        system_prompt = (
            "You are a document analysis assistant. Analyze the provided image based on the surrounding text context. "
            "Return a JSON object with two fields: 'title' (a 10-word technical alt-text) and 'analysis' "
            "(a detailed technical description of the image content for a RAG system)."
        )

        user_prompt = f"Surrounding context from the document:\n{context_text}"
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

        logger.info(
            f"Sending Open API Request with system_prompt: {system_prompt[:500]}, user_prompt: {user_prompt[:500]}"
        )

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model, messages=messages_content, temperature=0.2
                )

                content = response.choices[0].message.content
                try:
                    # Use json_repair to handle potential non-JSON or malformed JSON responses
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
                        f"Rate limit (429) hit for {image_path}. Attempt {attempt + 1}/{self.max_retries}. Retrying in {self.retry_delay}s..."
                    )
                    await asyncio.sleep(self.retry_delay)
                    continue
                else:
                    logger.error(f"Max retries reached for 429 error on {image_path}")
                    raise e
            except Exception as e:
                logger.error(f"VLM analysis failed for {image_path}: {e}")
                raise e
