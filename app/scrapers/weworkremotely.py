"""
We Work Remotely (WWR) RSS scraper.

Parses RSS feeds from WeWorkRemotely to extract remote job listings.

Notes:
    - Multiple feeds are consumed and results are deduplicated by URL.
    - Company names are extracted from RSS title (format: "Company: Job Title").
    - All WWR jobs are remote by definition.
    - Uses the ``feedparser`` library for RSS parsing.
"""

from __future__ import annotations

import json
import logging
from calendar import timegm
from datetime import datetime
from time import struct_time
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# RSS feed URLs to consume
_FEED_URLS: list[str] = [
    "https://weworkremotely.com/remote-jobs.rss",
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
]


class WeWorkRemotelyScraper(BaseScraper):
    """Scraper for We Work Remotely RSS feeds."""

    source_name: str = "weworkremotely"
    base_url: str = "https://weworkremotely.com"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch and merge job entries from all WWR RSS feeds.

        Deduplicates across feeds using the entry ``link`` as a unique key.

        Returns:
            List of raw feed-entry dicts.
        """
        import feedparser

        client = await self._get_client()
        seen_urls: set[str] = set()
        all_entries: list[dict[str, Any]] = []

        for feed_url in _FEED_URLS:
            try:
                response = await client.get(feed_url)
                response.raise_for_status()
                feed = feedparser.parse(response.text)

                for entry in feed.entries:
                    link = getattr(entry, "link", "")
                    if link and link not in seen_urls:
                        seen_urls.add(link)
                        all_entries.append(entry)

                self.logger.info(
                    "Fetched %d entries from %s (total unique: %d)",
                    len(feed.entries),
                    feed_url,
                    len(all_entries),
                )
            except httpx.HTTPStatusError as exc:
                self.logger.error(
                    "WWR feed HTTP error for %s: %s", feed_url, exc
                )
            except (httpx.RequestError, Exception) as exc:
                self.logger.error(
                    "WWR feed request failed for %s: %s", feed_url, exc
                )

        self.logger.info(
            "Total unique jobs from WWR feeds: %d", len(all_entries)
        )
        return all_entries

    def normalize(self, raw: Any) -> dict[str, Any]:
        """Normalize a feedparser entry to canonical schema.

        Args:
            raw: A ``feedparser.FeedParserDict`` entry.

        Returns:
            Dict matching the ``Job`` model fields.
        """
        full_title: str = getattr(raw, "title", "")
        company, title = self._parse_title(full_title)
        link: str = getattr(raw, "link", "")
        description_html: str = (
            getattr(raw, "summary", "")
            or getattr(raw, "description", "")
            or ""
        )
        published: datetime | None = self._parse_struct_time(
            getattr(raw, "published_parsed", None)
        )

        return {
            "title": title,
            "company": company,
            "location": "Remote",
            "remote": True,
            "salary": None,
            "employment_type": None,
            "experience": None,
            "skills": None,
            "description": self._clean_html(description_html),
            "url": link,
            "source": self.source_name,
            "posted_date": published,
            "scraped_at": datetime.utcnow(),
            "match_score": None,
            "ai_summary": None,
            "fingerprint": self._generate_fingerprint(
                title, company, "Remote"
            ),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_title(full_title: str) -> tuple[str, str]:
        """Extract ``(company, job_title)`` from a WWR RSS title.

        Common formats:
            - "Company Name: Job Title"
            - "Job Title" (no separator → company unknown)
        """
        if ":" in full_title:
            parts = full_title.split(":", maxsplit=1)
            return parts[0].strip(), parts[1].strip()
        return "Unknown", full_title.strip()

    @staticmethod
    def _parse_struct_time(st: struct_time | None) -> datetime | None:
        """Convert a ``time.struct_time`` to a ``datetime`` (UTC)."""
        if st is None:
            return None
        try:
            return datetime.utcfromtimestamp(timegm(st))
        except Exception:
            return None
