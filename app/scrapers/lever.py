"""
Lever job postings scraper.

Fetches job listings from Lever's public postings API for each company
that has a ``lever_token`` in the database.

Endpoint:
    ``GET https://api.lever.co/v0/postings/{company_slug}``

Notes:
    - ``createdAt`` is a Unix timestamp in **milliseconds**.
    - ``workplaceType`` indicates "remote", "onsite", or "hybrid".
    - Company slugs come from ``Company.lever_token``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class LeverScraper(BaseScraper):
    """Scraper for Lever public job postings."""

    source_name: str = "lever"
    base_url: str = "https://api.lever.co/v0/postings"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch jobs from all active Lever company boards.

        Returns:
            Aggregated list of raw posting dicts, each augmented with
            ``_company_name``.
        """
        from app.database.engine import SessionLocal
        from app.database.models import Company

        db = SessionLocal()
        try:
            companies = (
                db.query(Company)
                .filter(
                    Company.lever_token.isnot(None),
                    Company.lever_token != "",
                    Company.is_active.is_(True),
                )
                .all()
            )
        finally:
            db.close()

        if not companies:
            self.logger.info("No active Lever boards configured")
            return []

        client = await self._get_client()
        all_jobs: list[dict[str, Any]] = []

        for company in companies:
            slug: str = company.lever_token  # type: ignore[assignment]
            company_name: str = company.name  # type: ignore[assignment]
            url = f"{self.base_url}/{slug}"

            try:
                response = await client.get(url)
                response.raise_for_status()
                jobs: list[dict[str, Any]] = response.json()

                if not isinstance(jobs, list):
                    self.logger.warning(
                        "Lever returned non-list for '%s': %s",
                        slug,
                        type(jobs).__name__,
                    )
                    continue

                for job in jobs:
                    job["_company_name"] = company_name

                all_jobs.extend(jobs)
                self.logger.info(
                    "Fetched %d jobs from Lever board '%s' (%s)",
                    len(jobs),
                    slug,
                    company_name,
                )
            except httpx.HTTPStatusError as exc:
                self.logger.error(
                    "Lever HTTP error for slug '%s': %s", slug, exc
                )
            except (httpx.RequestError, Exception) as exc:
                self.logger.error(
                    "Lever request failed for slug '%s': %s", slug, exc
                )

        return all_jobs

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw Lever posting dict to canonical schema.

        Args:
            raw: Single posting record from the Lever API, augmented
                with ``_company_name``.

        Returns:
            Dict matching the ``Job`` model fields.
        """
        categories: dict[str, Any] = raw.get("categories") or {}
        location: str = (categories.get("location") or "").strip()
        commitment: str = (categories.get("commitment") or "").strip()
        team: str = (categories.get("team") or "").strip()

        workplace_type: str = (raw.get("workplaceType") or "").lower()
        remote = workplace_type == "remote"

        # Build skills from team + commitment
        skills_list: list[str] = [s for s in [team, commitment] if s]

        # Parse createdAt (millisecond Unix timestamp)
        posted_date: datetime | None = None
        created_at = raw.get("createdAt")
        if created_at:
            try:
                posted_date = datetime.utcfromtimestamp(int(created_at) / 1000)
            except (ValueError, TypeError, OSError):
                posted_date = None

        company_name: str = raw.get("_company_name", "")

        return {
            "title": (raw.get("text") or "").strip(),
            "company": company_name,
            "location": location or None,
            "remote": remote,
            "salary": None,
            "employment_type": commitment or None,
            "experience": None,
            "skills": json.dumps(skills_list) if skills_list else None,
            "description": self._clean_html(raw.get("description", "")),
            "url": (raw.get("hostedUrl") or raw.get("applyUrl") or "").strip(),
            "source": self.source_name,
            "posted_date": posted_date,
            "scraped_at": datetime.utcnow(),
            "match_score": None,
            "ai_summary": None,
            "fingerprint": self._generate_fingerprint(
                raw.get("text", ""),
                company_name,
                location,
            ),
        }
