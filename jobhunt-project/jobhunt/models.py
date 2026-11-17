"""models.py - the "shapes" of our data.

A dataclass is a plain Python class that mostly just holds data. Python writes
__init__ for us, so we only list the fields. Every other file imports these
shapes, so the whole project speaks the same language.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class Company:
    """One line in companies.yaml."""
    name: str   # Human friendly name, e.g. "Stripe"
    ats: str    # Which job board system: "greenhouse", "lever" or "ashby"
    slug: str   # The company's id on that system (the bit in the URL)


@dataclass
class Job:
    """A single job posting, normalised so all 3 ATS systems look the same."""
    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    source: str                          # "greenhouse" / "lever" / "ashby" / "mock"
    posted_at: Optional[datetime] = None  # Timezone-aware UTC datetime, if known

    @property
    def uid(self) -> str:
        """A globally unique id used for de-duplication in seen.json."""
        return f"{self.source}:{self.company}:{self.id}"


@dataclass
class Profile:
    """What Gemini learned from the resume. Saved to profile.json."""
    name: str = ""
    skills: list[str] = field(default_factory=list)
    years_experience: float = 0
    target_roles: list[str] = field(default_factory=list)
    education: str = ""
    summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScoredJob:
    """A job plus Gemini's opinion of it."""
    job: Job
    score: int                                   # 0-100
    reasoning: str                               # one-sentence explanation
    matched_skills: list[str] = field(default_factory=list)
    cover_letter: str = ""                       # only filled for the top jobs

    def to_dict(self) -> dict:
        return {
            "title": self.job.title,
            "company": self.job.company,
            "location": self.job.location,
            "url": self.job.url,
            "score": self.score,
            "reasoning": self.reasoning,
            "matched_skills": self.matched_skills,
            "cover_letter": self.cover_letter,
        }


@dataclass
class Config:
    """Settings from config.yaml (what the user wants)."""
    titles_include: list[str] = field(default_factory=list)
    titles_exclude: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    max_age_days: int = 14
    score_threshold: int = 70
    top_n_drafts: int = 3
    gemini_model: str = "gemini-2.0-flash"


@dataclass
class EnvSettings:
    """Secrets from .env (never commit these to Git!)."""
    gemini_api_key: str = ""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""
