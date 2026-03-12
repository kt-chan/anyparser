import asyncio
import hashlib
from openai import AsyncOpenAI, RateLimitError
from app.core.config import settings
from loguru import logger

class LLMClient:
    _semaphore = asyncio.Semaphore(5)  # Class-level semaphore for all instances
    _cache = {} # Class-level cache for all instances

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.LLM_API_KEY, base_url=settings.LLM_HOST_PATH
        )
        self.model = settings.LLM_MODEL_NAME
        self.max_retries = 3
        self.retry_delay = 2

    def _get_cache_key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def summarize(self, text: str, context_summaries: str = "") -> str:
        """
        Summarizes the text. If context_summaries is provided, it's a parent section summary.
        """
        if not text.strip() and not context_summaries.strip():
            return ""

        cache_key = self._get_cache_key(text + context_summaries)
        if cache_key in self._cache:
            logger.debug("LLM cache hit")
            return self._cache[cache_key]

        system_prompt = "You are a document summarization assistant. Summarize the provided text concisely in text paragraph (up to 5 sentences or 100 words)."
        
        user_prompt = f"Text to summarize:\n{text}"
        if context_summaries:
            user_prompt += f"\n\nContext (summaries of sub-sections):\n{context_summaries}"

        for attempt in range(self.max_retries + 1):
            try:
                async with self._semaphore:
                    logger.info(f"LLM Request - Model: {self.model}")
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.3
                    )
                summary = response.choices[0].message.content.strip()
                self._cache[cache_key] = summary
                return summary
            except RateLimitError as e:
                if attempt < self.max_retries:
                    logger.warning(f"LLM Rate limit hit, retrying in {self.retry_delay}s...")
                    await asyncio.sleep(self.retry_delay)
                    continue
                raise e
            except Exception as e:
                logger.error(f"LLM summarization failed: {e}")
                raise e

    async def analyze_table(
        self,
        table_content: str,
        document_summary: str,
        heading_path: str,
        section_summary: str,
        surrounding_text: str
    ) -> str:
        """
        Analyzes a table and returns a technical contextual description.
        """
        system_prompt = (
            "You are a document analysis assistant. Analyze the provided table based on its global and local document context. "
            "Provide a summarized description in text paragraph (up to 5 sentences or 100 words) explaining how the table data supports the document context."
        )

        user_prompt = (
            f"**Document Purpose:** {document_summary}\n"
            f"**Document Catalog:** {heading_path}\n"
            f"**Section Summary:** {section_summary}\n"
            f"**Immediate Text:** {surrounding_text[:500]}\n\n"
            f"**Table Data:**\n{table_content}\n\n"
            "**Task:** Provide a detailed technical description explaining how this table supports the section summary above."
        )

        logger.info("LLM Request - Table Analysis")
        for attempt in range(self.max_retries + 1):
            try:
                async with self._semaphore:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.3
                    )
                return response.choices[0].message.content.strip()
            except RateLimitError as e:
                if attempt < self.max_retries:
                    logger.warning(f"LLM Rate limit hit, retrying in {self.retry_delay}s...")
                    await asyncio.sleep(self.retry_delay)
                    continue
                raise e
            except Exception as e:
                logger.error(f"LLM table analysis failed: {e}")
                raise e
