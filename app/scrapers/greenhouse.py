"""
Greenhouse job board scraper.

Fetches job listings from Greenhouse's public board API for each company
that has a ``greenhouse_token`` in the database.

Endpoint:
    ``GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true``

Notes:
    - The ``content=true`` query parameter is required to get full HTML
      job descriptions.
    - Board tokens are sourced from the ``Company`` model's
      ``greenhouse_token`` field.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class GreenhouseScraper(BaseScraper):
    """Scraper for Greenhouse public job boards."""

    source_name: str = "greenhouse"
    base_url: str = "https://boards-api.greenhouse.io/v1/boards"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch jobs from all active Greenhouse boards.

        Queries the ``Company`` table for rows with a non-null
        ``greenhouse_token`` and ``is_active=True``, then fetches each
        board's listings.

        Returns:
            Aggregated list of raw job dicts, each augmented with
            ``_company_name`` for normalization.
        """
        from app.database.engine import SessionLocal
        from app.database.models import Company

        db = SessionLocal()
        try:
            companies = (
                db.query(Company)
                .filter(
                    Company.greenhouse_token.isnot(None),
                    Company.greenhouse_token != "",
                    Company.is_active.is_(True),
                )
                .all()
            )
        finally:
            db.close()

        if not companies:
            self.logger.info("No active Greenhouse boards configured")
            return []

        client = await self._get_client()
        all_jobs: list[dict[str, Any]] = []

        for company in companies:
            token: str = company.greenhouse_token  # type: ignore[assignment]
            company_name: str = company.name  # type: ignore[assignment]
            url = f"{self.base_url}/{token}/jobs"

            try:
                response = await client.get(url, params={"content": "true"})
                response.raise_for_status()
                data = response.json()
                jobs: list[dict[str, Any]] = data.get("jobs", [])

                # Attach company name for normalization
                for job in jobs:
                    job["_company_name"] = company_name

                all_jobs.extend(jobs)
                self.logger.info(
                    "Fetched %d jobs from Greenhouse board '%s' (%s)",
                    len(jobs),
                    token,
                    company_name,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    self.logger.warning(
                        "Greenhouse board for '%s' returned 404 (Not Found). It may have migrated to a different ATS.",
                        token,
                    )
                else:
                    self.logger.error(
                        "Greenhouse HTTP error for board '%s': %s", token, exc
                    )
            except (httpx.RequestError, Exception) as exc:
                self.logger.error(
                    "Greenhouse request failed for board '%s': %s", token, exc
                )

        return all_jobs

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw Greenhouse job dict to canonical schema.

        Args:
            raw: Single job record from the Greenhouse API, augmented
                with ``_company_name``.

        Returns:
            Dict matching the ``Job`` model fields.
        """
        location_obj = raw.get("location") or {}
        location: str = (
            location_obj.get("name", "")
            if isinstance(location_obj, dict)
            else str(location_obj)
        ).strip()

        # Departments → skills proxy
        departments: list[str] = [
            d.get("name", "")
            for d in (raw.get("departments") or [])
            if d.get("name")
        ]

        # Detect remote from location string
        remote = bool(
            location and "remote" in location.lower()
        )

        company_name: str = raw.get("_company_name", "")

        return {
            "title": (raw.get("title") or "").strip(),
            "company": company_name,
            "location": location or None,
            "remote": remote,
            "salary": None,
            "employment_type": None,
            "experience": None,
            "skills": json.dumps(departments) if departments else None,
            "description": self._clean_html(raw.get("content", "")),
            "url": (raw.get("absolute_url") or "").strip(),
            "source": self.source_name,
            "posted_date": self._parse_date(raw.get("updated_at")),
            "scraped_at": datetime.utcnow(),
            "match_score": None,
            "ai_summary": None,
            "fingerprint": self._generate_fingerprint(
                raw.get("title", ""),
                company_name,
                location,
            ),
        }
