import io
import re
from typing import Any, BinaryIO, Dict, List, Union
from pypdf import PdfReader

# Master skill catalogue for keyword matching
COMMON_SKILLS: List[str] = [
    # Programming Languages
    "Python", "JavaScript", "TypeScript", "Java", "C++", "C#", "Go", "Rust", "Ruby", "PHP", "SQL",
    # Frameworks & Libraries
    "Django", "Flask", "FastAPI", "React", "Next.js", "Vue", "Angular", "Node.js", "Express",
    # Databases & Storage
    "PostgreSQL", "MySQL", "SQLite", "MongoDB", "Redis", "Elasticsearch",
    # DevOps, Cloud & Tools
    "Docker", "Kubernetes", "AWS", "Azure", "GCP", "Git", "GitHub", "Linux", "CI/CD",
    # Web & Automation
    "REST API", "GraphQL", "Playwright", "Selenium", "Celery", "BeautifulSoup",
    # Data & AI
    "Machine Learning", "Pandas", "NumPy", "TensorFlow", "PyTorch", "OpenAI", "LLM"
]

EDUCATION_KEYWORDS: List[str] = [
    "Bachelor", "Master", "PhD", "Doctorate", "B.Sc", "M.Sc", "B.S.", "M.S.",
    "B.Tech", "M.Tech", "Computer Science", "Software Engineering", "University", "College"
]


def extract_text_from_pdf(pdf_source: Union[str, BinaryIO, bytes]) -> str:
    """
    Extracts text content from a PDF file path, open binary stream, or bytes buffer.
    
    Args:
        pdf_source: A file path string, Django UploadedFile, or raw bytes.
        
    Returns:
        str: Clean concatenated text from all readable pages.
        
    Raises:
        ValueError: If the file is unreadable, corrupted, or password-protected.
    """
    try:
        if isinstance(pdf_source, bytes):
            stream: BinaryIO = io.BytesIO(pdf_source)
            reader = PdfReader(stream)
        else:
            reader = PdfReader(pdf_source)

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as decrypt_err:
                raise ValueError("PDF is encrypted with a password and cannot be read.") from decrypt_err

        page_texts: List[str] = []
        for index, page in enumerate(reader.pages):
            extracted = page.extract_text()
            if extracted:
                page_texts.append(extracted.strip())

        full_text = "\n\n".join(page_texts).strip()
        if not full_text:
            return ""
        return full_text
    except Exception as exc:
        raise ValueError(f"Failed to process PDF file: {str(exc)}") from exc


def parse_resume_metadata(text: str) -> Dict[str, Any]:
    """
    Parses key candidate details from resume plain text using regex and heuristics.
    
    Args:
        text: Plain text representation of the resume.
        
    Returns:
        dict: Extracted contact information, detected skills, education, and counts.
    """
    if not text:
        return {
            "email": "",
            "phone": "",
            "skills": [],
            "education": [],
            "years_experience": None,
            "word_count": 0,
            "character_count": 0,
        }

    # 1. Email extraction regex
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    email_match = re.search(email_pattern, text)
    email = email_match.group(0).lower() if email_match else ""

    # 2. Phone extraction regex (handles international and local formats)
    phone_pattern = r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
    phone_match = re.search(phone_pattern, text)
    phone = phone_match.group(0).strip() if phone_match else ""

    # 3. Skills extraction using word-boundary matching
    text_lower = text.lower()
    matched_skills: List[str] = []
    for skill in COMMON_SKILLS:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, text_lower):
            matched_skills.append(skill)

    # 4. Education mentions
    matched_education: List[str] = []
    for edu in EDUCATION_KEYWORDS:
        if edu.lower() in text_lower and edu not in matched_education:
            matched_education.append(edu)

    # 5. Estimated years of experience
    exp_pattern = r"(\d{1,2})\+?\s*years?\s*(?:of)?\s*(?:professional\s*)?experience"
    exp_match = re.search(exp_pattern, text, re.IGNORECASE)
    years_experience = int(exp_match.group(1)) if exp_match else None

    return {
        "email": email,
        "phone": phone,
        "skills": matched_skills,
        "education": matched_education,
        "years_experience": years_experience,
        "word_count": len(text.split()),
        "character_count": len(text),
    }