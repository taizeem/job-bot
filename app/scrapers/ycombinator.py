"""
Y Combinator / Hacker News Jobs scraper.

Fetches job postings from the Hacker News Firebase API.

Pipeline:
    1. ``GET /v0/jobstories.json`` → array of item IDs.
    2. For each ID, ``GET /v0/item/{id}.json`` → item details.

Notes:
    - Title format: "CompanyName (YC W24) Is Hiring Engineers" — the
      company name is parsed from the title.
    - Concurrency is capped at 10 parallel requests with small delays
      to avoid hammering the API.
    - Total items capped at ``settings.max_jobs_per_source``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Regex to extract company name from HN job titles
# Matches: "CompanyName (YC W24) Is Hiring…" or "CompanyName Is Hiring…"
_COMPANY_RE = re.compile(
    r"^(?P<company>.+?)\s*(?:\(YC\s+\w+\))?\s*(?:is\s+hiring|–|—|-|:|\|)",
    re.IGNORECASE,
)


class YCombinatorScraper(BaseScraper):
    """Scraper for Hacker News (Y Combinator) job stories."""

    source_name: str = "ycombinator"
    base_url: str = "https://hacker-news.firebaseio.com/v0"

    _MAX_CONCURRENCY: int = 10
    _REQUEST_DELAY: float = 0.1  # seconds between batches

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch HN job stories with concurrency-limited batching.

        Returns:
            List of raw item dicts from the HN Firebase API.
        """
        # Import settings for max_jobs_per_source
        try:
            from app.config import settings

            max_items: int = getattr(settings, "max_jobs_per_source", 200)
        except Exception:
            max_items = 200

        client = await self._get_client()

        # Step 1: Get job story IDs
        try:
            response = await client.get(f"{self.base_url}/jobstories.json")
            response.raise_for_status()
            story_ids: list[int] = response.json() or []
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            self.logger.error("Failed to fetch HN job story IDs: %s", exc)
            return []

        # Cap the number of items
        story_ids = story_ids[:max_items]
        self.logger.info(
            "Fetching details for %d HN job stories", len(story_ids)
        )

        # Step 2: Fetch item details in batches
        semaphore = asyncio.Semaphore(self._MAX_CONCURRENCY)
        items: list[dict[str, Any]] = []

        async def _fetch_item(item_id: int) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    resp = await client.get(
                        f"{self.base_url}/item/{item_id}.json"
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if data and isinstance(data, dict):
                        return data
                except Exception as exc:
                    self.logger.debug(
                        "Failed to fetch HN item %d: %s", item_id, exc
                    )
                return None

        # Process in batches to add inter-batch delays
        batch_size = self._MAX_CONCURRENCY
        for i in range(0, len(story_ids), batch_size):
            batch = story_ids[i : i + batch_size]
            results = await asyncio.gather(
                *[_fetch_item(sid) for sid in batch],
                return_exceptions=True,
            )
            for result in results:
                if isinstance(result, dict):
                    items.append(result)
                elif isinstance(result, Exception):
                    self.logger.debug("HN batch exception: %s", result)

            # Small delay between batches
            if i + batch_size < len(story_ids):
                await asyncio.sleep(self._REQUEST_DELAY)

        self.logger.info(
            "Successfully fetched %d/%d HN job items",
            len(items),
            len(story_ids),
        )
        return items

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw HN job item to canonical schema.

        Args:
            raw: Single item dict from the HN Firebase API.

        Returns:
            Dict matching the ``Job`` model fields.
        """
        title: str = (raw.get("title") or "").strip()
        company = self._extract_company(title)
        url: str = (raw.get("url") or "").strip()

        # If no external URL, construct HN item link
        if not url:
            item_id = raw.get("id")
            url = (
                f"https://news.ycombinator.com/item?id={item_id}"
                if item_id
                else ""
            )

        # Parse unix timestamp
        posted_date: datetime | None = None
        unix_time = raw.get("time")
        if unix_time:
            try:
                posted_date = datetime.utcfromtimestamp(int(unix_time))
            except (ValueError, TypeError, OSError):
                posted_date = None

        # Description from 'text' field (HTML)
        description = self._clean_html(raw.get("text", ""))

        return {
            "title": title,
            "company": company,
            "location": None,
            "remote": None,
            "salary": None,
            "employment_type": None,
            "experience": None,
            "skills": None,
            "description": description,
            "url": url,
            "source": self.source_name,
            "posted_date": posted_date,
            "scraped_at": datetime.utcnow(),
            "match_score": None,
            "ai_summary": None,
            "fingerprint": self._generate_fingerprint(
                title, company, ""
            ),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_company(title: str) -> str:
        """Parse company name from an HN job title.

        Examples:
            - "Acme Corp (YC W24) Is Hiring Engineers" → "Acme Corp"
            - "Startup – Full Stack Developer" → "Startup"
            - "Hiring at Google" → "Google" (fallback)
        """
        match = _COMPANY_RE.match(title)
        if match:
            return match.group("company").strip()

        # Fallback: try "Hiring at CompanyName"
        hiring_at = re.search(
            r"hiring\s+at\s+(.+)", title, re.IGNORECASE
        )
        if hiring_at:
            return hiring_at.group(1).strip()

        return "Unknown"
