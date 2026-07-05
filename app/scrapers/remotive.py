"""
Remotive job scraper.

Fetches remote job listings from the Remotive API at
``https://remotive.com/api/remote-jobs``.

Notes:
    - Rate limit: max 2 requests/minute, ideally ≤4 requests/day.
    - Supports optional query parameters: ``category``, ``company_name``,
      ``limit``, ``search``.
    - Job descriptions are returned as HTML and cleaned to plain text.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Mapping from Remotive's job_type values → human-readable format
_JOB_TYPE_MAP: dict[str, str] = {
    "full_time": "Full-time",
    "part_time": "Part-time",
    "contract": "Contract",
    "freelance": "Freelance",
    "internship": "Internship",
    "other": "Other",
}


class RemotiveScraper(BaseScraper):
    """Scraper for the Remotive remote-jobs API."""

    source_name: str = "remotive"
    base_url: str = "https://remotive.com/api/remote-jobs"

    def __init__(
        self,
        category: str | None = None,
        company_name: str | None = None,
        limit: int | None = None,
        search: str | None = None,
    ) -> None:
        super().__init__()
        self._params: dict[str, str | int] = {}
        if category:
            self._params["category"] = category
        if company_name:
            self._params["company_name"] = company_name
        if limit:
            self._params["limit"] = limit
        if search:
            self._params["search"] = search

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch raw job listings from Remotive.

        Returns:
            List of raw job dicts from the ``jobs`` key of the response.
        """
        client = await self._get_client()

        try:
            response = await client.get(self.base_url, params=self._params)
            response.raise_for_status()
            data = response.json()
            jobs: list[dict[str, Any]] = data.get("jobs", [])
            self.logger.info(
                "Fetched %d raw jobs from Remotive", len(jobs)
            )
            return jobs

        except httpx.HTTPStatusError as exc:
            self.logger.error(
                "Remotive HTTP error %s: %s",
                exc.response.status_code,
                exc,
            )
            return []
        except (httpx.RequestError, Exception) as exc:
            self.logger.error("Remotive request failed: %s", exc)
            return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw Remotive job dict to canonical schema.

        Args:
            raw: Single job record from the Remotive API.

        Returns:
            Dict matching the ``Job`` model fields.
        """
        job_type_raw: str = (raw.get("job_type") or "").strip().lower()
        employment_type = _JOB_TYPE_MAP.get(job_type_raw, job_type_raw.replace("_", " ").title() or None)

        tags: list[str] = raw.get("tags") or []
        location = (raw.get("candidate_required_location") or "Remote").strip()

        return {
            "title": (raw.get("title") or "").strip(),
            "company": (raw.get("company_name") or "").strip(),
            "location": location,
            "remote": True,
            "salary": (raw.get("salary") or "").strip() or None,
            "employment_type": employment_type if employment_type else None,
            "experience": None,
            "skills": json.dumps(tags) if tags else None,
            "description": self._clean_html(raw.get("description", "")),
            "url": (raw.get("url") or "").strip(),
            "source": self.source_name,
            "posted_date": self._parse_date(raw.get("publication_date")),
            "scraped_at": datetime.utcnow(),
            "match_score": None,
            "ai_summary": None,
            "fingerprint": self._generate_fingerprint(
                raw.get("title", ""),
                raw.get("company_name", ""),
                location,
            ),
        }
