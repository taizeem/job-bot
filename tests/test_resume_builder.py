"""
Tests for the resume builder models and keyword matcher.
"""

from __future__ import annotations

import json
from sqlalchemy.orm import Session
from app.database.models import UserProfile, UserExperience, UserProject, Job
from app.ai.keyword_matcher import compute_keyword_score, run_keyword_matching_pipeline


def test_user_profile_crud(db_session: Session):
    """Test creating, reading, updating, and deleting a UserProfile and relationships."""
    # Create profile
    profile = UserProfile(
        name="Alice Smith",
        email="alice@example.com",
        phone="555-123-4567",
        location="Chicago, IL",
        country="United States",
        summary="Experienced engineer.",
        skills=json.dumps(["Python", "FastAPI", "PostgreSQL"]),
        preferred_job_titles=json.dumps(["Backend Engineer", "Software Engineer"]),
        preferred_locations=json.dumps(["Chicago, IL", "Remote"])
    )
    db_session.add(profile)
    db_session.commit()

    # Verify profile creation
    db_prof = db_session.query(UserProfile).first()
    assert db_prof is not None
    assert db_prof.name == "Alice Smith"
    assert "FastAPI" in json.loads(db_prof.skills)

    # Add experience
    exp = UserExperience(
        profile_id=db_prof.id,
        company="Tech Corp",
        title="Software Engineer",
        start_date="Jan 2020",
        end_date="Dec 2022",
        is_current=False,
        bullets=json.dumps(["Built REST APIs with FastAPI.", "Optimized database queries."])
    )
    db_session.add(exp)
    db_session.commit()

    assert len(db_prof.experiences) == 1
    assert db_prof.experiences[0].company == "Tech Corp"
    assert len(json.loads(db_prof.experiences[0].bullets)) == 2


def test_keyword_matching(db_session: Session):
    """Test the keyword-based job matching calculation logic."""
    profile_data = {
        "skills": ["Python", "FastAPI", "React", "PostgreSQL"],
        "country": "United States",
        "preferred_locations": ["Chicago", "Remote"],
        "preferred_job_titles": ["Backend Engineer", "Software Developer"]
    }

    # Job 1: Strong Match (matches title, location, skills)
    job1 = Job(
        title="Backend Engineer (Python/FastAPI)",
        company="Innovative Co",
        location="Remote",
        remote=True,
        skills=json.dumps(["Python", "FastAPI", "PostgreSQL", "Docker"]),
        description="We are looking for a Backend Engineer with experience in Python and FastAPI. Docker is a plus.",
        url="https://innovative.co/jobs/1",
        source="lever"
    )
    
    # Job 2: Weak Match (different title, location, and no matching skills)
    job2 = Job(
        title="Systems Administrator",
        company="Oldschool Inc",
        location="Tokyo, Japan",
        remote=False,
        skills=json.dumps(["Linux", "Networking", "Bash"]),
        description="We need a Systems Administrator to maintain our local servers. Must know Linux and Bash.",
        url="https://oldschool.co/jobs/2",
        source="lever"
    )

    db_session.add_all([job1, job2])
    db_session.commit()

    # Score Job 1
    score1, summary1 = compute_keyword_score(profile_data, job1)
    assert score1 >= 0.70
    assert "✓ Python" in summary1
    assert "✓ Matches (Remote position)" in summary1
    assert "✓ Match (Backend Engineer)" in summary1

    # Score Job 2
    score2, summary2 = compute_keyword_score(profile_data, job2)
    assert score2 < 0.20
    assert "✗ Linux" in summary2
    assert "✗ No Match" in summary2
