from django.apps import AppConfig


class JobsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "jobs"
    verbose_name = "Job Application Automation"

    def ready(self):
        """Connect signal handlers when the Django application boots up."""
        import jobs.signals  # noqa: F401