import json
import logging
from typing import Any, Dict, List, Optional
from django.conf import settings
import ollama

logger = logging.getLogger(__name__)


class AIMatchingEngine:
    """Evaluates candidate fit against job descriptions using local Ollama or keyword heuristics."""

    def __init__(self):
        self.base_url: str = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        self.model_name: str = getattr(settings, "OLLAMA_MODEL", "llama3.2")
        self.client = ollama.Client(host=self.base_url)

    def evaluate_fit(
        self,
        resume_text: str,
        resume_skills: List[str],
        job_title: str,
        job_description: str,
        required_skills: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates match score (0.0 to 100.0), strengths, missing skills, and tailored cover letter.
        """
        required_skills = required_skills or []

        # 1. Attempt local Ollama inference
        try:
            return self._evaluate_with_ollama(
                resume_text=resume_text,
                resume_skills=resume_skills,
                job_title=job_title,
                job_description=job_description,
            )
        except Exception as exc:
            logger.warning(
                f"Ollama local inference failed ({exc}). "
                "Ensure Ollama is running ('ollama serve'). Falling back to heuristic matching."
            )

        # 2. Heuristic fallback (fast, offline, deterministic)
        return self._evaluate_heuristic(
            resume_text=resume_text,
            resume_skills=resume_skills,
            job_title=job_title,
            job_description=job_description,
            required_skills=required_skills,
        )

    def _build_prompt(self, resume_text: str, resume_skills: List[str], job_title: str, job_description: str) -> str:
        return f"""You are an expert technical recruiter and talent evaluation system.
Compare the Candidate Resume against the Target Job Description.

CANDIDATE RESUME SUMMARY:
{resume_text[:2000]}

CANDIDATE DETECTED SKILLS:
{', '.join(resume_skills) if resume_skills else 'None specified'}

TARGET JOB:
Title: {job_title}
Description:
{job_description[:2000]}

Respond ONLY with a valid JSON object matching this schema:
{{
  "match_score": <float between 0.0 and 100.0>,
  "summary": "<2-sentence clear explanation of fit>",
  "matching_skills": ["<skill1>", "<skill2>"],
  "missing_skills": ["<skillA>", "<skillB>"],
  "cover_letter": "<3-paragraph concise, professional cover letter tailored to this role>"
}}
"""

    def _evaluate_with_ollama(
        self,
        resume_text: str,
        resume_skills: List[str],
        job_title: str,
        job_description: str,
    ) -> Dict[str, Any]:
        prompt = self._build_prompt(resume_text, resume_skills, job_title, job_description)

        response = self.client.chat(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": "You are a specialized AI recruitment scoring engine. You output valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            format="json",
            options={"temperature": 0.2},
        )

        # Handle dict or object response structure from ollama client
        if isinstance(response, dict):
            content = response.get("message", {}).get("content", "{}")
        else:
            content = getattr(response.message, "content", "{}")

        parsed_json = json.loads(content)
        return self._sanitize_response(parsed_json)

    def _evaluate_heuristic(
        self,
        resume_text: str,
        resume_skills: List[str],
        job_title: str,
        job_description: str,
        required_skills: List[str],
    ) -> Dict[str, Any]:
        """Calculates match based on keyword intersection when Ollama is unavailable."""
        text_lower = (resume_text + " " + " ".join(resume_skills)).lower()
        job_lower = (job_title + " " + job_description + " " + " ".join(required_skills)).lower()

        sample_keywords = [
            "python", "django", "fastapi", "flask", "react", "javascript", "typescript",
            "docker", "kubernetes", "aws", "postgresql", "sql", "git", "linux", "rest", "api"
        ]
        target_skills = set(required_skills or [k for k in sample_keywords if k in job_lower])
        if not target_skills:
            target_skills = {"python", "django", "git"}

        matching: List[str] = [s for s in target_skills if s.lower() in text_lower]
        missing: List[str] = [s for s in target_skills if s.lower() not in text_lower]

        overlap_ratio = len(matching) / len(target_skills) if target_skills else 0.5
        score = round(min(100.0, max(20.0, overlap_ratio * 100.0)), 1)

        cover_letter = (
            f"Dear Hiring Team,\n\n"
            f"I am writing to express my strong interest in the {job_title} position. "
            f"With hands-on experience in {', '.join(matching[:3]) if matching else 'software engineering'}, "
            f"I am well-equipped to contribute immediately to your team.\n\n"
            f"My technical background aligns with your core requirements, and I would welcome the opportunity to discuss how I can support your engineering objectives.\n\n"
            f"Sincerely,\nCandidate"
        )

        return {
            "match_score": score,
            "summary": f"Candidate matches {len(matching)}/{len(target_skills)} core skills required for {job_title}.",
            "matching_skills": matching,
            "missing_skills": missing,
            "cover_letter": cover_letter,
        }

    def _sanitize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Ensures score is bounded and all expected fields exist."""
        try:
            score = float(data.get("match_score", 50.0))
        except (ValueError, TypeError):
            score = 50.0
        score = max(0.0, min(100.0, score))

        return {
            "match_score": round(score, 1),
            "summary": str(data.get("summary", "Evaluation complete.")),
            "matching_skills": list(data.get("matching_skills", [])),
            "missing_skills": list(data.get("missing_skills", [])),
            "cover_letter": str(data.get("cover_letter", "")),
        }