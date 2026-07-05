"""
Scraper orchestrator for the AI Job Hunting Agent.

Provides :func:`run_all_scrapers` which concurrently executes every
configured job scraper, deduplicates the results, and persists new
jobs to the database.

Usage::

    import asyncio
    from app.scrapers import run_all_scrapers

    summary = asyncio.run(run_all_scrapers())
    print(summary)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.scrapers.ashby import AshbyScraper
from app.scrapers.greenhouse import GreenhouseScraper
from app.scrapers.lever import LeverScraper
from app.scrapers.remoteok import RemoteOKScraper
from app.scrapers.remotive import RemotiveScraper
from app.scrapers.weworkremotely import WeWorkRemotelyScraper
from app.scrapers.ycombinator import YCombinatorScraper
from app.scrapers.dedup import store_jobs
from app.database.engine import SessionLocal

logger = logging.getLogger("scrapers")

# Re-export individual scraper classes for convenience
__all__ = [
    "run_all_scrapers",
    "AshbyScraper",
    "GreenhouseScraper",
    "LeverScraper",
    "RemoteOKScraper",
    "RemotiveScraper",
    "WeWorkRemotelyScraper",
    "YCombinatorScraper",
]


async def run_all_scrapers() -> dict[str, Any]:
    """Run all scrapers, deduplicate, store, and return a summary.

    Scrapers execute concurrently via ``asyncio.gather``. Individual
    scraper failures are caught and logged — they never crash the
    whole pipeline.

    Returns:
        A summary dict with keys:
            - ``total_scraped``: Total jobs found across all sources.
            - ``new_jobs``: Jobs actually inserted into the DB.
            - ``duplicates``: Jobs skipped as duplicates.
            - ``per_source``: Breakdown per scraper source.
    """
    scrapers = [
        RemoteOKScraper(),
        RemotiveScraper(),
        WeWorkRemotelyScraper(),
        GreenhouseScraper(),
        LeverScraper(),
        AshbyScraper(),
        YCombinatorScraper(),
    ]

    all_jobs: list[dict[str, Any]] = []
    per_source: dict[str, dict[str, Any]] = {}

    # Run all scrapers concurrently
    results = await asyncio.gather(
        *[s.scrape() for s in scrapers],
        return_exceptions=True,
    )

    for scraper, result in zip(scrapers, results):
        if isinstance(result, BaseException):
            logger.error(
                "%s failed with exception: %s", scraper.source_name, result
            )
            per_source[scraper.source_name] = {
                "scraped": 0,
                "error": str(result),
            }
        else:
            all_jobs.extend(result)
            per_source[scraper.source_name] = {"scraped": len(result)}

    logger.info(
        "Total jobs scraped across all sources: %d", len(all_jobs)
    )

    # Store with deduplication
    new_count = 0
    db = SessionLocal()
    try:
        new_count = store_jobs(all_jobs, db)
    except Exception as exc:
        logger.error("Failed to store jobs: %s", exc)
    finally:
        db.close()

    summary: dict[str, Any] = {
        "total_scraped": len(all_jobs),
        "new_jobs": new_count,
        "duplicates": len(all_jobs) - new_count,
        "per_source": per_source,
    }

    logger.info(
        "Scrape complete — total: %d, new: %d, duplicates: %d",
        summary["total_scraped"],
        summary["new_jobs"],
        summary["duplicates"],
    )

    return summary
