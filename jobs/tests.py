import io
import json
from unittest.mock import MagicMock, patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from pypdf import PdfWriter

from .automation import JobApplicationBot
from .forms import ApplicationStatusUpdateForm, ResumeUploadForm
from .matching import AIMatchingEngine
from .models import Application, ApplicationLog, JobListing, Resume
from .notifications import TelegramNotificationService
from .parsers import extract_text_from_pdf, parse_resume_metadata
from .services import JobApplicationPipeline


def generate_test_pdf_bytes(text_lines: list[str]) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.getvalue()


class ResumeParserTests(TestCase):
    def test_parse_resume_metadata_success(self):
        sample = """
        Jane Doe
        Email: jane@test.com | Phone: (555) 000-1111
        Engineer with 4 years of experience in Python, Django, Docker, AWS.
        Education: Bachelor of Science.
        """
        parsed = parse_resume_metadata(sample)
        self.assertEqual(parsed["email"], "jane@test.com")
        self.assertEqual(parsed["phone"], "(555) 000-1111")
        self.assertEqual(parsed["years_experience"], 4)
        self.assertIn("Python", parsed["skills"])
        self.assertIn("Django", parsed["skills"])

    def test_extract_text_from_corrupted_file(self):
        with self.assertRaises(ValueError):
            extract_text_from_pdf(b"INVALID_HEADER")


class AIMatchingEngineTests(TestCase):
    def setUp(self):
        self.engine = AIMatchingEngine()

    def test_heuristic_high_match(self):
        resume_text = "Experienced with Python, Django, PostgreSQL, Docker, Git, and Linux."
        resume_skills = ["Python", "Django", "PostgreSQL", "Docker"]
        result = self.engine.evaluate_fit(
            resume_text=resume_text,
            resume_skills=resume_skills,
            job_title="Django Backend Developer",
            job_description="Seeking a Python and Django developer with PostgreSQL and Docker.",
            required_skills=["Python", "Django", "PostgreSQL", "Docker"],
        )
        self.assertGreaterEqual(result["match_score"], 80.0)
        self.assertIn("Python", result["matching_skills"])
        self.assertIn("cover_letter", result)


class JobApplicationBotTests(TestCase):
    def test_simulation_url_success(self):
        bot = JobApplicationBot(headless=True)
        res = bot.submit_application(
            job_url="simulation://test-portal/apply",
            candidate_name="Alex Mercer",
            candidate_email="alex@test.com",
            candidate_phone="555-0100",
            resume_path=None,
        )
        self.assertTrue(res["success"])
        self.assertIn("simulated successfully", res["message"])


class WebDashboardAndViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.resume = Resume.objects.create(
            name="Sarah Connor",
            parsed_text="Full Stack Python and Django Specialist",
            extracted_skills=["Python", "Django"],
            metadata={"email": "sarah@connor.dev", "phone": "555-4321"},
        )
        self.job = JobListing.objects.create(
            title="Python Developer",
            company="Cyberdyne Systems",
            description="Django, Python, and SQLite.",
            required_skills=["Python", "Django"],
            url="simulation://cyberdyne.com/job/1",
        )
        self.application = Application.objects.create(
            resume=self.resume,
            job=self.job,
            match_score=85.0,
            status=Application.STATUS_APPLIED,
        )

    def test_dashboard_view_loads_successfully(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "jobs/dashboard.html")

    def test_update_status_view(self):
        response = self.client.post(
            reverse("update_status", args=[self.application.id]),
            {"status": Application.STATUS_APPLIED, "notes": "Application confirmed."},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.application.refresh_from_db()
        self.assertEqual(self.application.status, Application.STATUS_APPLIED)


class TelegramNotificationTests(TestCase):
    def setUp(self):
        self.service = TelegramNotificationService(bot_token="test_token", chat_id="123456")

    @patch("jobs.notifications.requests.post")
    def test_send_message_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 99}}
        mock_post.return_value = mock_response

        res = self.service.send_message("Test message")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["result"]["message_id"], 99)

    def test_service_unconfigured_skips_call(self):
        unconfigured_service = TelegramNotificationService(bot_token="", chat_id="")
        self.assertFalse(unconfigured_service.is_configured)
        res = unconfigured_service.send_message("Hello")
        self.assertFalse(res["success"])
        self.assertIn("missing or unconfigured", res["error"])


class TelegramSignalIntegrationTests(TestCase):
    def setUp(self):
        self.resume = Resume.objects.create(name="Signal Test Candidate")
        self.job = JobListing.objects.create(
            title="Backend Lead",
            company="Starlight Labs",
            description="Django, Python",
            url="simulation://starlight.io/1",
        )
        self.application = Application.objects.create(
            resume=self.resume,
            job=self.job,
            match_score=91.0,
            status=Application.STATUS_APPLIED,
        )

    @patch("jobs.notifications.TelegramNotificationService.send_message")
    def test_transition_to_interview_triggers_signal_and_logs(self, mock_send):
        mock_send.return_value = {"success": True, "data": {}}

        # Transition status to INTERVIEW
        self.application.status = Application.STATUS_INTERVIEW
        self.application.notes = "Round 1 interview scheduled with Engineering VP."
        self.application.save()

        # Check that Telegram send_message was triggered
        self.assertTrue(mock_send.called)

        # Check that an ApplicationLog was written for the Telegram dispatch
        log_entry = ApplicationLog.objects.filter(
            application=self.application,
            message__icontains="Telegram alert sent",
        ).first()
        self.assertIsNotNone(log_entry)

    @patch("jobs.notifications.TelegramNotificationService.send_message")
    def test_saving_without_status_change_does_not_retrigger(self, mock_send):
        mock_send.return_value = {"success": True}

        # Saving while staying in APPLIED should NOT fire interview signal
        self.application.notes = "Updated notes only."
        self.application.save()

        self.assertFalse(mock_send.called)