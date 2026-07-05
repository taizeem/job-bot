"""
RemoteOK job scraper.

Fetches remote job listings from the RemoteOK JSON API at
``https://remoteok.io/api``.

Notes:
    - The first element of the response array is a legal notice (no ``id``
      field) and is automatically skipped.
    - All jobs on RemoteOK are remote by definition.
    - HTTP 429 responses trigger an automatic retry with exponential backoff.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class RemoteOKScraper(BaseScraper):
    """Scraper for the RemoteOK remote-jobs API."""

    source_name: str = "remoteok"
    base_url: str = "https://remoteok.io/api"

    # Retry configuration for HTTP 429
    _MAX_RETRIES: int = 3
    _INITIAL_BACKOFF: float = 5.0  # seconds

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch raw job listings from RemoteOK.

        Returns:
            List of raw job dicts (legal-notice element already removed).

        Raises:
            httpx.HTTPStatusError: On non-429 HTTP errors after retries.
        """
        client = await self._get_client()
        backoff = self._INITIAL_BACKOFF

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                response = await client.get(self.base_url)

                if response.status_code == 429:
                    retry_after = float(
                        response.headers.get("Retry-After", backoff)
                    )
                    self.logger.warning(
                        "RemoteOK rate-limited (429). Retrying in %.1fs "
                        "(attempt %d/%d)",
                        retry_after,
                        attempt,
                        self._MAX_RETRIES,
                    )
                    await asyncio.sleep(retry_after)
                    backoff *= 2
                    continue

                response.raise_for_status()
                data: list[dict[str, Any]] = response.json()

                # First element is the legal notice — skip anything without 'id'
                jobs = [item for item in data if "id" in item]
                self.logger.info(
                    "Fetched %d raw jobs from RemoteOK", len(jobs)
                )
                return jobs

            except httpx.HTTPStatusError as exc:
                self.logger.error(
                    "RemoteOK HTTP error %s (attempt %d/%d): %s",
                    exc.response.status_code,
                    attempt,
                    self._MAX_RETRIES,
                    exc,
                )
                if attempt == self._MAX_RETRIES:
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2

            except (httpx.RequestError, json.JSONDecodeError) as exc:
                self.logger.error(
                    "RemoteOK request failed (attempt %d/%d): %s",
                    attempt,
                    self._MAX_RETRIES,
                    exc,
                )
                if attempt == self._MAX_RETRIES:
                    return []
                await asyncio.sleep(backoff)
                backoff *= 2

        return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw RemoteOK job dict to canonical schema.

        Args:
            raw: Single job record from the RemoteOK API.

        Returns:
            Dict matching the ``Job`` model fields.
        """
        salary = self._build_salary(
            raw.get("salary_min"), raw.get("salary_max")
        )
        tags: list[str] = raw.get("tags") or []

        return {
            "title": raw.get("position", "").strip(),
            "company": raw.get("company", "").strip(),
            "location": raw.get("location", "Remote"),
            "remote": True,
            "salary": salary,
            "employment_type": None,
            "experience": None,
            "skills": json.dumps(tags) if tags else None,
            "description": self._clean_html(raw.get("description", "")),
            "url": raw.get("url", "").strip(),
            "source": self.source_name,
            "posted_date": self._parse_date(raw.get("date")),
            "scraped_at": datetime.utcnow(),
            "match_score": None,
            "ai_summary": None,
            "fingerprint": self._generate_fingerprint(
                raw.get("position", ""),
                raw.get("company", ""),
                raw.get("location", ""),
            ),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_salary(
        salary_min: int | str | None,
        salary_max: int | str | None,
    ) -> str | None:
        """Format min/max into a human-readable salary string."""
        try:
            lo = int(salary_min) if salary_min else 0
            hi = int(salary_max) if salary_max else 0
        except (ValueError, TypeError):
            return None

        if lo and hi:
            return f"${lo:,} - ${hi:,}"
        if lo:
            return f"${lo:,}+"
        if hi:
            return f"Up to ${hi:,}"
        return None
