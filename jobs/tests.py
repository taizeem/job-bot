import io
import json
from unittest.mock import MagicMock, patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from pypdf import PdfWriter

from .automation import JobApplicationBot
from .matching import AIMatchingEngine
from .models import Application, ApplicationLog, JobListing, Resume
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

    def test_heuristic_low_match(self):
        resume_text = "Proficient in Python and Django."
        resume_skills = ["Python", "Django"]
        result = self.engine.evaluate_fit(
            resume_text=resume_text,
            resume_skills=resume_skills,
            job_title="Embedded Firmware Engineer",
            job_description="Requires C, C++, Assembly, microcontrollers, and hardware schematics.",
            required_skills=["C++", "Assembly", "Microcontrollers"],
        )
        self.assertLessEqual(result["match_score"], 40.0)
        self.assertIn("missing_skills", result)

    @patch("jobs.matching.ollama.Client")
    def test_ollama_matching_mock(self, mock_client_class):
        mock_client = MagicMock()
        mock_response = {
            "message": {
                "content": json.dumps({
                    "match_score": 92.0,
                    "summary": "Excellent fit for backend role.",
                    "matching_skills": ["Python", "Django"],
                    "missing_skills": ["AWS"],
                    "cover_letter": "I am excited to apply for this position.",
                })
            }
        }
        mock_client.chat.return_value = mock_response
        mock_client_class.return_value = mock_client

        engine = AIMatchingEngine()
        result = engine.evaluate_fit(
            resume_text="Python Django developer with 5 years experience.",
            resume_skills=["Python", "Django"],
            job_title="Backend Developer",
            job_description="Looking for Python and Django.",
            required_skills=["Python", "Django"],
        )
        self.assertEqual(result["match_score"], 92.0)
        self.assertIn("Python", result["matching_skills"])
        self.assertEqual(result["summary"], "Excellent fit for backend role.")


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


class PipelineOrchestratorTests(TestCase):
    def setUp(self):
        self.resume = Resume.objects.create(
            name="Test Candidate",
            parsed_text="Python Django Docker PostgreSQL",
            extracted_skills=["Python", "Django", "Docker", "PostgreSQL"],
            metadata={"email": "candidate@test.com", "phone": "555-9999"},
        )
        self.matching_job = JobListing.objects.create(
            title="Senior Python Engineer",
            company="Alpha Tech",
            description="We need Python, Django, Docker.",
            required_skills=["Python", "Django", "Docker"],
            url="simulation://alphatech.com/apply/1",
        )
        self.non_matching_job = JobListing.objects.create(
            title="Swift iOS Developer",
            company="Beta Mobile",
            description="Requires Swift, SwiftUI, iOS.",
            required_skills=["Swift", "SwiftUI", "iOS"],
            url="simulation://betamobile.com/apply/2",
        )

    def test_pipeline_applies_only_to_high_matches(self):
        pipeline = JobApplicationPipeline(match_threshold=70.0, headless=True)
        results = pipeline.run_for_resume(self.resume, job_limit=10, dry_run=False)

        # High match should be applied
        matching_app = Application.objects.get(job=self.matching_job, resume=self.resume)
        self.assertEqual(matching_app.status, Application.STATUS_APPLIED)
        self.assertIsNotNone(matching_app.applied_at)
        self.assertGreaterEqual(matching_app.match_score, 70.0)

        # Low match should remain pending
        non_matching_app = Application.objects.get(job=self.non_matching_job, resume=self.resume)
        self.assertEqual(non_matching_app.status, Application.STATUS_PENDING)
        self.assertIsNone(non_matching_app.applied_at)

        # Verify audit logs
        self.assertGreater(matching_app.logs.count(), 0)
        self.assertGreater(non_matching_app.logs.count(), 0)