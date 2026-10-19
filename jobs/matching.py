import json
import logging
import re
from typing import Any, Dict, List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class AIMatchingEngine:
    """Evaluates candidate fit against job descriptions using LLMs or local heuristics."""

    def __init__(self):
        self.openai_key: str = getattr(settings, "OPENAI_API_KEY", "")
        self.gemini_key: str = getattr(settings, "GEMINI_API_KEY", "")

    def evaluate_fit(
        self,
        resume_text: str,
        resume_skills: List[str],
        job_title: str,
        job_description: str,
        required_skills: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Calculates match score (0-100), key strengths, gaps, and generates a tailored cover letter.
        """
        required_skills = required_skills or []

        # 1. Try OpenAI if API key is configured
        if self.openai_key and self.openai_key.startswith("sk-"):
            try:
                return self._evaluate_with_openai(
                    resume_text=resume_text,
                    resume_skills=resume_skills,
                    job_title=job_title,
                    job_description=job_description,
                )
            except Exception as exc:
                logger.warning(f"OpenAI matching failed, falling back: {exc}")

        # 2. Try Gemini if API key is configured
        if self.gemini_key and not self.gemini_key.startswith("your_"):
            try:
                return self._evaluate_with_gemini(
                    resume_text=resume_text,
                    resume_skills=resume_skills,
                    job_title=job_title,
                    job_description=job_description,
                )
            except Exception as exc:
                logger.warning(f"Gemini matching failed, falling back: {exc}")

        # 3. Deterministic local heuristic fallback (offline & test friendly)
        return self._evaluate_heuristic(
            resume_text=resume_text,
            resume_skills=resume_skills,
            job_title=job_title,
            job_description=job_description,
            required_skills=required_skills,
        )

    def _build_prompt(self, resume_text: str, resume_skills: List[str], job_title: str, job_description: str) -> str:
        return f"""You are an expert technical recruiter and talent evaluator.
Analyze the fit between this Candidate Resume and the Job Posting.

CANDIDATE RESUME EXTRACT:
{resume_text[:2500]}

CANDIDATE DETECTED SKILLS:
{', '.join(resume_skills) if resume_skills else 'Not specified'}

JOB POSTING:
Role: {job_title}
Description:
{job_description[:2500]}

Respond ONLY with a valid JSON object matching this schema:
{{
  "match_score": <number between 0.0 and 100.0>,
  "summary": "<2-sentence objective summary of fit>",
  "matching_skills": ["<skill1>", "<skill2>"],
  "missing_skills": ["<skillA>", "<skillB>"],
  "cover_letter": "<3-paragraph concise, professional cover letter tailored to this role>"
}}
Do not include markdown fences (```json) or extra text outside the JSON object.
"""

    def _evaluate_with_openai(
        self,
        resume_text: str,
        resume_skills: List[str],
        job_title: str,
        job_description: str,
    ) -> Dict[str, Any]:
        from openai import OpenAI

        client = OpenAI(api_key=self.openai_key)
        prompt = self._build_prompt(resume_text, resume_skills, job_title, job_description)

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a specialized JSON-only recruitment evaluation engine."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        return self._sanitize_response(json.loads(content))

    def _evaluate_with_gemini(
        self,
        resume_text: str,
        resume_skills: List[str],
        job_title: str,
        job_description: str,
    ) -> Dict[str, Any]:
        import google.generativeai as genai

        genai.configure(api_key=self.gemini_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = self._build_prompt(resume_text, resume_skills, job_title, job_description)

        response = model.generate_content(prompt)
        text = response.text.strip()
        # Strip potential markdown formatting
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return self._sanitize_response(json.loads(text))

    def _evaluate_heuristic(
        self,
        resume_text: str,
        resume_skills: List[str],
        job_title: str,
        job_description: str,
        required_skills: List[str],
    ) -> Dict[str, Any]:
        """Calculates a deterministic match based on keyword intersection."""
        text_lower = (resume_text + " " + " ".join(resume_skills)).lower()
        job_lower = (job_title + " " + job_description + " " + " ".join(required_skills)).lower()

        # Extract words from job description that resemble skills
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
            f"I am confident in my ability to contribute effectively from day one.\n\n"
            f"My background aligns closely with your technical requirements, and I am eager to help your team achieve its goals.\n\n"
            f"Sincerely,\nCandidate"
        )

        return {
            "match_score": score,
            "summary": f"Candidate demonstrates proficiency in {len(matching)}/{len(target_skills)} core skills for {job_title}.",
            "matching_skills": matching,
            "missing_skills": missing,
            "cover_letter": cover_letter,
        }

    def _sanitize_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validates and enforces clean structure and numerical bounds."""
        score = float(data.get("match_score", 50.0))
        score = max(0.0, min(100.0, score))
        return {
            "match_score": round(score, 1),
            "summary": str(data.get("summary", "Match evaluation completed.")),
            "matching_skills": list(data.get("matching_skills", [])),
            "missing_skills": list(data.get("missing_skills", [])),
            "cover_letter": str(data.get("cover_letter", "")),
        }