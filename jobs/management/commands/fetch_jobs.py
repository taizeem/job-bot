from django.core.management.base import BaseCommand
from jobs.fetcher import JobFetcherService


class Command(BaseCommand):
    help = "Fetches fresh software engineering jobs from public APIs"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10, help="Max jobs to fetch (default: 10)")

    def handle(self, *args, **options):
        limit = options["limit"]
        self.stdout.write(self.style.NOTICE(f"Fetching up to {limit} live tech jobs..."))

        fetcher = JobFetcherService()
        jobs = fetcher.fetch_and_store_jobs(limit=limit)

        self.stdout.write(self.style.SUCCESS(f"Successfully stored {len(jobs)} new job postings."))
        for j in jobs:
            self.stdout.write(f"• {j.title} at {j.company} ({j.location})")