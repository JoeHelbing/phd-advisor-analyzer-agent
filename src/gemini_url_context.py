from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from google import genai  # type: ignore[reportAttributeAccessIssue]
from google.genai import types
from pydantic_ai.usage import RequestUsage
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.config import SETTINGS

logger = logging.getLogger(__name__)


class UrlRetrievalError(Exception):
    """Raised when URL context retrieval fails and should be retried."""
    pass


@dataclass(frozen=True, slots=True)
class GeminiPaperReviewConfig:
    """Configuration for Gemini paper review service."""
    model: str = "gemini-3-flash-preview"
    max_attempts: int = 3
    retry_backoff: float = 1.5
    fallback_bytes: bool = True
    download_timeout: float = 30.0
    max_concurrent_requests: int | None = 5  # None = unlimited

    @classmethod
    def from_settings(cls) -> GeminiPaperReviewConfig:
        """Create config from settings (currently uses defaults)."""
        return cls()


@dataclass(slots=True)
class GeminiSummaryResult:
    text: str
    status: str | None
    strategy: str
    metadata: dict[str, Any]
    usage: RequestUsage
    error: str | None = None


@dataclass
class _UrlContextResult:
    """Result from URL context attempt."""
    response_text: str
    response_dump: dict[str, Any]
    usage: RequestUsage
    status: str | None
    metadata: dict[str, Any]


def create_async_client(api_key: str) -> genai.Client:
    """Create async Gemini client.

    Args:
        api_key: Google AI Studio API key

    Returns:
        Async Gemini client instance

    Raises:
        ValueError: If api_key is empty
    """
    if not api_key:
        raise ValueError("Missing Google AI Studio API key.")
    return genai.Client(api_key=api_key).aio


class GeminiPaperReviewService:
    """Service for reviewing academic papers using Gemini URL Context API.

    Handles:
    - Client instance management
    - Rate limiting via internal semaphore
    - Retry logic with exponential backoff
    - URL context with fallback to inline PDF
    - Prompt building and response parsing
    """

    def __init__(
        self,
        client: Any,
        config: GeminiPaperReviewConfig | None = None,
    ):
        """Initialize paper review service.

        Args:
            client: Async Gemini client from create_async_client()
            config: Service configuration (defaults to GeminiPaperReviewConfig())

        Raises:
            ValueError: If client doesn't have required 'models' attribute
        """
        if not hasattr(client, "models"):
            raise ValueError("Gemini client must expose a models attribute.")

        self._client = client
        self._config = config or GeminiPaperReviewConfig()

        # Create semaphore for rate limiting if configured
        self._semaphore: asyncio.Semaphore | None = None
        if self._config.max_concurrent_requests:
            self._semaphore = asyncio.Semaphore(
                self._config.max_concurrent_requests
            )

    @property
    def client(self) -> Any:
        """Access underlying Gemini client (for testing/inspection)."""
        return self._client

    @property
    def config(self) -> GeminiPaperReviewConfig:
        """Access service configuration."""
        return self._config

    async def summarize_paper(
        self,
        *,
        title: str,
        url: str,
        interests: str,
    ) -> GeminiSummaryResult:
        """Summarize a paper PDF using Gemini URL Context.

        This is the main entry point for paper review. It attempts to use
        Gemini URL Context first, then falls back to inline PDF upload if
        URL context fails after retries.

        Args:
            title: Paper title for context
            url: Direct URL to paper PDF
            interests: User's research interests document

        Returns:
            GeminiSummaryResult with summary text, status, and metadata
        """
        logger.debug("Starting paper review for: %s", title)
        prompt = self._build_prompt(title, url, interests)
        logger.debug("Prompt length: %d chars", len(prompt))
        tools = [types.Tool(urlContext=types.UrlContext())]  # type: ignore[reportCallIssue]

        # Try URL context approach first
        try:
            result = await self._attempt_url_context(
                prompt=prompt,
                tools=tools,
                title=title,
                url=url,
            )
            logger.debug(
                "✓ URL context succeeded for '%s' (status=%s, tokens: in=%d out=%d cache=%d)",
                title,
                result.status,
                result.usage.input_tokens or 0,
                result.usage.output_tokens or 0,
                result.usage.cache_read_tokens or 0,
            )
            return GeminiSummaryResult(
                text=result.response_text,
                status=result.status,
                strategy="url_context",
                metadata=result.metadata,
                usage=result.usage,
            )
        except UrlRetrievalError:
            logger.debug(
                "✗ URL context FAILED after %d attempts for '%s', initiating fallback strategy",
                self._config.max_attempts,
                title,
            )

        # Fallback to inline PDF if enabled
        if self._config.fallback_bytes:
            logger.debug("→ Starting fallback: inline PDF download for '%s'", title)
            return await self._attempt_fallback(prompt, url)

        # No fallback enabled, return failure
        logger.debug("✗ Fallback disabled - returning failure for '%s'", title)
        return GeminiSummaryResult(
            text="",
            status=None,
            strategy="url_context_failed",
            metadata={},
            usage=RequestUsage(),
            error="URL context failed and fallback disabled",
        )

    async def _attempt_url_context(
        self,
        prompt: str,
        tools: list[Any],
        title: str,
        url: str,
    ) -> _UrlContextResult:
        """Attempt Gemini URL Context with retry logic.

        Args:
            prompt: Complete prompt with instructions and context
            tools: Gemini tools list (URL context)
            title: Paper title (for logging)
            url: PDF URL (for logging)

        Returns:
            _UrlContextResult with response and metadata

        Raises:
            UrlRetrievalError: If URL context fails after all retries
        """
        retry_decorator = self._make_retry_decorator()

        @retry_decorator
        async def _attempt():
            logger.debug("Gemini URL Context attempt for %s (%s)", title, url)

            call = self._client.models.generate_content(
                model=self._config.model,
                contents=prompt,
                config=types.GenerateContentConfig(tools=tools),  # type: ignore[reportArgumentType]
            )

            if self._semaphore:
                logger.debug("Waiting for semaphore (rate limit) for '%s'...", title)
                response = await self._run_with_semaphore(call)
            else:
                response = await call

            response_text = response.text or ""
            response_dump = response.model_dump()
            usage = self._extract_usage(response_dump)
            status = self._extract_url_context_status(response_dump)
            metadata = {
                "url_context_metadata": response_dump.get("url_context_metadata")
                or response_dump.get("candidates", [{}])[0].get(
                    "url_context_metadata", {}
                ),
            }

            if status == "URL_RETRIEVAL_STATUS_ERROR":
                logger.debug(
                    "Gemini URL Context failed with status=%s; will retry",
                    status,
                )
                raise UrlRetrievalError(
                    f"URL retrieval failed with status: {status}"
                )

            return _UrlContextResult(
                response_text=response_text,
                response_dump=response_dump,
                usage=usage,
                status=status,
                metadata=metadata,
            )

        return await _attempt()

    async def _attempt_fallback(
        self,
        prompt: str,
        url: str,
    ) -> GeminiSummaryResult:
        """Attempt inline PDF fallback strategy.

        Downloads the PDF and sends it inline with the request.

        Args:
            prompt: Complete prompt with instructions and context
            url: PDF URL to download

        Returns:
            GeminiSummaryResult with summary or error
        """
        logger.debug("Attempting inline PDF fallback for %s", url)
        strategy = "fallback_inline_pdf_failed"
        response_dump: dict[str, Any] = {}

        try:
            pdf_bytes = await self._download_pdf_bytes(url)
            logger.debug("Downloaded PDF: %d bytes from %s", len(pdf_bytes), url)
            call = self._client.models.generate_content(
                model=self._config.model,
                contents=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(
                        data=pdf_bytes,
                        mime_type="application/pdf",
                    ),
                ],
            )

            if self._semaphore:
                logger.debug("Waiting for semaphore (rate limit) for fallback...")
                response = await self._run_with_semaphore(call)
            else:
                response = await call

            response_text = response.text or ""
            response_dump = response.model_dump()
            usage = self._extract_usage(response_dump)
            status = self._extract_url_context_status(response_dump)
            metadata = {
                "fallback": "inline_pdf",
                "url_context_metadata": response_dump.get("url_context_metadata")
                or response_dump.get("candidates", [{}])[0].get(
                    "url_context_metadata", {}
                ),
            }
            strategy = "fallback_inline_pdf"
            logger.debug(
                "✓ Inline PDF fallback SUCCEEDED for %s (tokens: in=%d out=%d cache=%d)",
                url,
                usage.input_tokens or 0,
                usage.output_tokens or 0,
                usage.cache_read_tokens or 0,
            )

            return GeminiSummaryResult(
                text=response_text,
                status=status,
                strategy=strategy,
                metadata=metadata,
                usage=usage,
            )

        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.debug("✗ Inline PDF fallback FAILED for %s: %s", url, error)
            metadata = {
                "fallback": "inline_pdf_failed",
                "url_context_metadata": response_dump.get("url_context_metadata")
                or response_dump.get("candidates", [{}])[0].get(
                    "url_context_metadata", {}
                ),
            }

            return GeminiSummaryResult(
                text="",
                status=None,
                strategy=strategy,
                metadata=metadata,
                usage=RequestUsage(),
                error=error,
            )

    def _build_prompt(self, title: str, url: str, interests: str) -> str:
        """Build the Gemini prompt with instructions and context.

        Loads instructions from SETTINGS and injects dynamic context.

        Args:
            title: Paper title
            url: Direct PDF URL
            interests: User's research interests document

        Returns:
            Complete prompt with instructions and injected context
        """
        instructions = SETTINGS.paper_review_agent.instructions

        context = (
            f"\n\n---\n\n"
            f"# INPUT\n\n"
            f"**Title:** {title}\n\n"
            f"**URL:** {url}\n\n"
            f"**Research interests:**\n{interests}\n"
        )

        return instructions + context

    async def _download_pdf_bytes(self, url: str) -> bytes:
        """Download PDF bytes from URL.

        Args:
            url: PDF URL to download

        Returns:
            PDF file bytes

        Raises:
            httpx.HTTPError: If download fails
        """
        async with httpx.AsyncClient(
            timeout=self._config.download_timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def _run_with_semaphore(self, coro: Any) -> Any:
        """Execute coroutine with semaphore rate limiting.

        Args:
            coro: Coroutine to execute

        Returns:
            Coroutine result
        """
        async with self._semaphore:  # type: ignore[union-attr]
            return await coro

    def _make_retry_decorator(self):
        """Create retry decorator with config-based parameters.

        Returns:
            Configured tenacity retry decorator
        """
        return retry(
            retry=retry_if_exception_type(UrlRetrievalError),
            stop=stop_after_attempt(self._config.max_attempts),
            wait=wait_exponential(
                multiplier=self._config.retry_backoff,
                min=1,
                max=10,
            ),
            reraise=True,
        )

    @staticmethod
    def _extract_url_context_status(response_dump: dict[str, Any]) -> str | None:
        """Extract URL context retrieval status from response.

        Args:
            response_dump: Gemini API response as dict

        Returns:
            URL retrieval status string or None if not found
        """
        metadata = response_dump.get("url_context_metadata")
        if metadata is None:
            metadata = response_dump.get("candidates", [{}])[0].get(
                "url_context_metadata",
                {},
            )
        if metadata and metadata.get("url_metadata"):
            return metadata["url_metadata"][0].get("url_retrieval_status")
        return None

    @staticmethod
    def _extract_usage(response_dump: dict[str, Any]) -> RequestUsage:
        """Extract usage metadata as pydantic-ai RequestUsage.

        Args:
            response_dump: Gemini API response as dict

        Returns:
            RequestUsage object with token counts
        """
        usage = response_dump.get("usage_metadata", {})
        if not usage:
            return RequestUsage()

        input_tokens = usage.get("prompt_token_count", 0)
        output_tokens = usage.get("response_token_count", 0)
        cache_tokens = usage.get("cached_content_token_count", 0)
        details = {
            "total_token_count": usage.get("total_token_count", 0),
            "tool_use_prompt_token_count": usage.get(
                "tool_use_prompt_token_count", 0
            ),
            "thoughts_token_count": usage.get("thoughts_token_count", 0),
            "prompt_tokens_details": usage.get("prompt_tokens_details"),
            "response_tokens_details": usage.get("response_tokens_details"),
            "cache_tokens_details": usage.get("cache_tokens_details"),
            "tool_use_prompt_tokens_details": usage.get(
                "tool_use_prompt_tokens_details"
            ),
            "traffic_type": usage.get("traffic_type"),
        }
        details = {k: v for k, v in details.items() if v}
        return RequestUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_tokens,
            details=details,
        )
