"""
Indeed job scraper — **STUB**.

Indeed's Terms of Service prohibit automated scraping.  This module
exists as a placeholder so the orchestrator can instantiate it without
errors, but it will **never** return any jobs.

If Indeed integration is needed in the future, consider:
    - Indeed's Publisher Program / Indeed Apply API.
    - Third-party aggregators with authorized access.
"""

from __future__ import annotations

import logging
from typing import Any

from app.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class IndeedScraper(BaseScraper):
    """Stub scraper for Indeed — always returns an empty list.

    Indeed prohibits automated scraping under its Terms of Service.
    This class is provided for interface completeness only.
    """

    source_name: str = "indeed"
    base_url: str = "https://www.indeed.com"

    async def fetch_jobs(self) -> list[dict[str, Any]]:
        """Return an empty list and log a warning.

        Returns:
            An empty list — no jobs are ever fetched.
        """
        self.logger.warning(
            "Indeed scraping is disabled — Terms of Service prohibit "
            "automated access. Use the Indeed Publisher API or a "
            "third-party provider instead."
        )
        return []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """No-op normalizer (never called).

        Args:
            raw: Unused.

        Returns:
            The input dict unchanged.
        """
        return raw
