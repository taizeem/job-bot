"""
Ashby job board scraper.

Fetches job listings from Ashby's public posting API for each company
that has an ``ashby_token`` in the database.

Endpoint:
    ``GET https://api.ashbyhq.com/posting-api/job-board/{board_name}?includeCompensation=true``

Notes:
    - ``employmentType`` values: "FullTime", "PartTime", "Contract", "Intern".
    - ``compensation.compensationTierSummary`` provides salary info.
    - Board names come from ``Company.ashby_token``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

# Mapping from Ashby's employmentType → readable format
_EMPLOYMENT_TYPE_MAP: dict[str, str] = {
    "FullTime": "Full-time",
    "fulltime": "Full-time",
    "PartTime": "Part-time",
    "parttime": "Part-time",
    "Contract": "Contract",
    "contract": "Contract",
    "Intern": "Internship",
    "intern": "Internship",
    "Internship": "Internship",
    "internship": "Internship",
}


class AshbyScraper(BaseScraper):
    """Scraper for Ashby public job boards."""

    source_name: str = "ashby"
    base_url: str = "https://api.ashbyhq.com/posting-api/job-board"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Fetch jobs from all active Ashby boards.

        Returns:
            Aggregated list of raw job dicts, each augmented with
            ``_company_name``.
        """
        from app.database.engine import SessionLocal
        from app.database.models import Company

        db = SessionLocal()
        try:
            companies = (
                db.query(Company)
                .filter(
                    Company.ashby_token.isnot(None),
                    Company.ashby_token != "",
                    Company.is_active.is_(True),
                )
                .all()
            )
        finally:
            db.close()

        if not companies:
            self.logger.info("No active Ashby boards configured")
            return []

        client = await self._get_client()
        all_jobs: list[dict[str, Any]] = []

        for company in companies:
            board_name: str = company.ashby_token  # type: ignore[assignment]
            company_name: str = company.name  # type: ignore[assignment]
            url = f"{self.base_url}/{board_name}"

            try:
                response = await client.get(
                    url, params={"includeCompensation": "true"}
                )
                response.raise_for_status()
                data = response.json()
                jobs: list[dict[str, Any]] = data.get("jobs", [])

                for job in jobs:
                    job["_company_name"] = company_name

                all_jobs.extend(jobs)
                self.logger.info(
                    "Fetched %d jobs from Ashby board '%s' (%s)",
                    len(jobs),
                    board_name,
                    company_name,
                )
            except httpx.HTTPStatusError as exc:
                self.logger.error(
                    "Ashby HTTP error for board '%s': %s", board_name, exc
                )
            except (httpx.RequestError, Exception) as exc:
                self.logger.error(
                    "Ashby request failed for board '%s': %s",
                    board_name,
                    exc,
                )

        return all_jobs

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Normalize a raw Ashby job dict to canonical schema.

        Args:
            raw: Single job record from the Ashby API, augmented with
                ``_company_name``.

        Returns:
            Dict matching the ``Job`` model fields.
        """
        location: str = (raw.get("location") or "").strip()
        remote = bool(location and "remote" in location.lower())

        # Employment type normalization
        raw_type: str = (raw.get("employmentType") or "").strip()
        employment_type = _EMPLOYMENT_TYPE_MAP.get(raw_type, raw_type or None)

        # Compensation
        compensation = raw.get("compensation") or {}
        salary: str | None = (
            compensation.get("compensationTierSummary") or ""
        ).strip() or None

        # Department & team → skills proxy
        skills_list: list[str] = []
        for field in ("department", "team"):
            val = raw.get(field)
            if val and isinstance(val, str) and val.strip():
                skills_list.append(val.strip())

        company_name: str = raw.get("_company_name", "")

        return {
            "title": (raw.get("title") or "").strip(),
            "company": company_name,
            "location": location or None,
            "remote": remote,
            "salary": salary,
            "employment_type": employment_type,
            "experience": None,
            "skills": json.dumps(skills_list) if skills_list else None,
            "description": self._clean_html(
                raw.get("descriptionHtml", "")
            ),
            "url": (
                raw.get("jobUrl") or raw.get("applyUrl") or ""
            ).strip(),
            "source": self.source_name,
            "posted_date": self._parse_date(raw.get("publishedAt")),
            "scraped_at": datetime.utcnow(),
            "match_score": None,
            "ai_summary": None,
            "fingerprint": self._generate_fingerprint(
                raw.get("title", ""),
                company_name,
                location,
            ),
        }
