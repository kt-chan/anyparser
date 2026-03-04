import asyncio
import hashlib
from openai import AsyncOpenAI, RateLimitError
from app.core.config import settings
from loguru import logger

class LLMClient:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY, base_url=settings.LLM_HOST_PATH
        )
        self.model = settings.LLM_MODEL_NAME
        self.max_retries = 3
        self.retry_delay = 2
        self.cache = {}

    def _get_cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def summarize(self, text: str, context_summaries: str = "") -> str:
        """
        Summarizes the text. If context_summaries is provided, it's a parent section summary.
        """
        if not text.strip() and not context_summaries.strip():
            return ""

        cache_key = self._get_cache_key(text + context_summaries)
        if cache_key in self.cache:
            return self.cache[cache_key]

        system_prompt = "You are a document summarization assistant. Summarize the provided text concisely (up to 5 sentences or 100 words)."
        
        user_prompt = f"Text to summarize:\n{text}"
        if context_summaries:
            user_prompt += f"\n\nContext (summaries of sub-sections):\n{context_summaries}"

        logger.info(f"LLM Request - Model: {self.model}")
        logger.info(f"LLM System Prompt: {system_prompt}")
        logger.info(f"LLM User Prompt: {user_prompt}")

        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3
                )
                summary = response.choices[0].message.content.strip()
                self.cache[cache_key] = summary
                return summary
            except RateLimitError as e:
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
                    continue
                raise e
            except Exception as e:
                logger.error(f"LLM summarization failed: {e}")
                raise e
