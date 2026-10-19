from django.contrib import admin
from .models import Application, ApplicationLog, JobListing, Resume


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ("name", "uploaded_at", "display_skills_count", "display_file_link")
    search_fields = ("name", "parsed_text")
    readonly_fields = ("uploaded_at", "parsed_text", "extracted_skills", "metadata")

    def display_skills_count(self, obj: Resume) -> int:
        return len(obj.extracted_skills)
    display_skills_count.short_description = "Skills Detected"

    def display_file_link(self, obj: Resume) -> str:
        if obj.file:
            return obj.file.name
        return "No file"
    display_file_link.short_description = "File Path"


@admin.register(JobListing)
class JobListingAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "location", "source", "created_at")
    list_filter = ("source", "location", "created_at")
    search_fields = ("title", "company", "description")


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "job",
        "resume",
        "match_score",
        "status",
        "applied_at",
        "updated_at",
    )
    list_filter = ("status", "created_at", "updated_at")
    search_fields = ("job__title", "job__company", "resume__name")
    list_editable = ("status",)


@admin.register(ApplicationLog)
class ApplicationLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "level", "application", "short_message")
    list_filter = ("level", "timestamp")
    search_fields = ("message", "application__job__title")
    readonly_fields = ("timestamp",)

    def short_message(self, obj: ApplicationLog) -> str:
        return obj.message[:80] + ("..." if len(obj.message) > 80 else "")
    short_message.short_description = "Log Message"