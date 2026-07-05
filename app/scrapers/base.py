"""
Abstract base class for all job scrapers.

Provides shared infrastructure: async HTTP client management, job
normalization pipeline, fingerprint generation for deduplication,
date parsing, and HTML-to-text cleaning.

Every concrete scraper must subclass ``BaseScraper`` and implement
:meth:`fetch_jobs` and :meth:`normalize`.
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import httpx


class BaseScraper(ABC):
    """Abstract base class for all job scrapers.

    Attributes:
        source_name: Human-readable identifier for the job source.
        base_url: Root URL used by the scraper.
    """

    source_name: str = "unknown"
    base_url: str = ""

    def __init__(self) -> None:
        self.logger: logging.Logger = logging.getLogger(
            f"scraper.{self.source_name}"
        )
        self.client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # HTTP client
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a reusable async HTTP client, creating one if needed."""
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                timeout=30.0,
                headers={"User-Agent": "JobBot/1.0"},
                follow_redirects=True,
            )
        return self.client

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch raw job listings from the remote source.

        Returns:
            A list of raw job dictionaries as returned by the source API.
        """
        ...

    @abstractmethod
    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Convert a raw job dict into the canonical Job schema.

        Args:
            raw: A single raw job record from :meth:`fetch_jobs`.

        Returns:
            A dictionary whose keys match the ``Job`` model fields.
        """
        ...

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    async def scrape(self) -> list[dict[str, Any]]:
        """Execute the full scrape→normalize pipeline.

        Returns:
            A list of normalized job dictionaries ready for storage.
        """
        self.logger.info("Starting scrape from %s", self.source_name)
        try:
            raw_jobs = await self.fetch_jobs()
            normalized: list[dict[str, Any]] = []
            for job in raw_jobs:
                try:
                    normalized.append(self.normalize(job))
                except Exception as exc:
                    self.logger.warning("Failed to normalize job: %s", exc)
                    continue
            self.logger.info(
                "Scraped %d jobs from %s", len(normalized), self.source_name
            )
            return normalized
        except Exception as exc:
            self.logger.error("Error scraping %s: %s", self.source_name, exc)
            return []
        finally:
            if self.client and not self.client.is_closed:
                await self.client.aclose()

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _generate_fingerprint(
        self,
        title: str,
        company: str,
        location: str = "",
    ) -> str:
        """Create a short, deterministic hash from job identity fields.

        This is used by the dedup module to detect semantically
        identical postings across different sources.
        """
        raw = (
            f"{title.lower().strip()}|"
            f"{company.lower().strip()}|"
            f"{location.lower().strip()}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Best-effort parse of a date string into a ``datetime``.

        Tries common ISO / human-readable formats via ``dateutil``.
        Returns ``None`` on failure instead of raising.
        """
        if not date_str:
            return None
        try:
            from dateutil import parser as dateutil_parser

            return dateutil_parser.parse(date_str)
        except Exception:
            return None

    def _clean_html(self, html: str) -> str:
        """Strip HTML tags and return plain text.

        Uses BeautifulSoup with the ``lxml`` parser for speed.
        """
        if not html:
            return ""
        try:
            from bs4 import BeautifulSoup

            return BeautifulSoup(html, "lxml").get_text(
                separator="\n", strip=True
            )
        except Exception:
            # Fallback: return raw string with tags naively stripped
            import re

            return re.sub(r"<[^>]+>", " ", html).strip()
