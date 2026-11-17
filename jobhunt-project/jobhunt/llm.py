"""llm.py - everything that talks to Google Gemini.

Three jobs for the AI:
  1. parse_resume()        resume text   -> Profile (JSON)
  2. score_job()           profile + job -> score 0-100 (JSON)
  3. draft_cover_letter()  profile + job -> short email text

Prompt-writing tips used here (good to mention in your presentation):
  * A SYSTEM prompt sets the AI's role and strict rules.
  * We spell out the exact JSON keys we want.
  * We ask Gemini for JSON mode (response_mime_type) AND still clean the
    reply in code, because we never fully trust AI output.
"""

import json
import logging
import re
import time

from google import genai
from google.genai import types
from jobhunt.models import Job, Profile

log = logging.getLogger("jobhunt")

MAX_DESC_CHARS = 3000  # cut long job descriptions to save tokens (= money)


class LLMError(Exception):
    """Raised when Gemini fails or returns something we can't use."""


# ---------------- Strict system prompts ----------------

RESUME_SYSTEM_PROMPT = """You are a resume parsing engine.
You receive the plain text of a resume and return ONLY a single JSON object.

RULES:
- Output raw JSON. No markdown, no code fences, no commentary before or after.
- Use EXACTLY these keys and types:
  {
    "name": string,
    "skills": [string],            // technical skills, tools, languages; max 30
    "years_experience": number,    // total years incl. internships; 0 if none
    "target_roles": [string],      // 2-5 job titles that fit this person
    "education": string,           // highest degree, field and school
    "summary": string              // 2 sentences describing the candidate
  }
- Only use information present in the resume. If something is missing, use
  "" for strings, [] for lists and 0 for numbers. Never invent facts.
"""

SCORING_SYSTEM_PROMPT = """You are a strict, honest job-matching engine.
You receive a candidate profile and a job posting. Return ONLY one JSON object.

RULES:
- Output raw JSON. No markdown, no code fences, no commentary.
- Use EXACTLY these keys and types:
  {
    "score": integer,              // 0-100
    "reasoning": string,           // ONE sentence, max 30 words
    "matched_skills": [string]     // candidate skills that the job asks for
  }
- Scoring guide: 90-100 excellent fit, 70-89 good fit, 40-69 partial fit,
  0-39 poor fit. Penalise jobs needing far more experience than the candidate has.
- Judge only from the text given. Do not invent requirements.
"""

COVER_LETTER_SYSTEM_PROMPT = """You write short, honest, professional job application emails.
RULES:
- Plain text only. No markdown, no subject line, no placeholders like [Name].
- 120-160 words, 3 short paragraphs, friendly but professional tone.
- Mention 2-3 REAL skills or facts from the candidate profile that match the job.
- Never claim experience the candidate does not have.
- Start with 'Dear Hiring Team,' and end with 'Best regards,' followed by the candidate's name.
"""


# ---------------- Helpers ----------------

def _clean_json(text: str) -> dict:
    """Even in JSON mode, models sometimes wrap output in ```json fences.
    Strip them, grab everything from the first { to the last }, then parse."""
    text = re.sub(r"```(?:json)?", "", text or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError("Gemini did not return a JSON object.")
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise LLMError(f"Gemini returned invalid JSON: {e}")


def _profile_to_text(profile: Profile) -> str:
    return json.dumps(profile.to_dict(), indent=2)


def _job_to_text(job: Job) -> str:
    return (f"Title: {job.title}\nCompany: {job.company}\n"
            f"Location: {job.location}\n"
            f"Description: {job.description[:MAX_DESC_CHARS]}")


# ---------------- The real Gemini client ----------------

class GeminiClient:
    def __init__(self, api_key: str, model_name: str):
        # timeout is in milliseconds: give up on a stuck request after 30 s
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=30_000),
        )
        self.model_name = model_name

    def _ask(self, system_prompt: str, user_prompt: str,
             as_json: bool = True, temperature: float = 0.2) -> str:
        """Send one request. Retry once if it fails (APIs have bad days)."""
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            response_mime_type="application/json" if as_json else "text/plain",
        )
        last_error = None
        for attempt in range(4):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name, contents=user_prompt, config=config)
                return response.text
            except Exception as e:
                last_error = e
                wait = 2 ** (attempt + 1)  # 2s, 4s, 8s, 16s: "exponential backoff"
                log.debug("Gemini attempt %d failed: %s", attempt + 1, e)
                if attempt < 3:
                    time.sleep(wait)
        raise LLMError(f"Gemini request failed: {last_error}")

    def parse_resume(self, resume_text: str) -> Profile:
        raw = self._ask(RESUME_SYSTEM_PROMPT, f"RESUME TEXT:\n{resume_text[:12000]}")
        data = _clean_json(raw)
        return Profile(
            name=str(data.get("name", "")),
            skills=[str(s) for s in data.get("skills", [])],
            years_experience=float(data.get("years_experience") or 0),
            target_roles=[str(r) for r in data.get("target_roles", [])],
            education=str(data.get("education", "")),
            summary=str(data.get("summary", "")),
        )

    def score_job(self, profile: Profile, job: Job) -> tuple[int, str, list[str]]:
        prompt = f"CANDIDATE PROFILE:\n{_profile_to_text(profile)}\n\nJOB POSTING:\n{_job_to_text(job)}"
        data = _clean_json(self._ask(SCORING_SYSTEM_PROMPT, prompt))
        score = max(0, min(100, int(data.get("score", 0))))  # clamp into 0-100
        return score, str(data.get("reasoning", "")), [str(s) for s in data.get("matched_skills", [])]

    def draft_cover_letter(self, profile: Profile, job: Job) -> str:
        prompt = f"CANDIDATE PROFILE:\n{_profile_to_text(profile)}\n\nJOB POSTING:\n{_job_to_text(job)}"
        return self._ask(COVER_LETTER_SYSTEM_PROMPT, prompt,
                         as_json=False, temperature=0.7).strip()


# ---------------- Mock versions (no API calls, no cost) ----------------

def mock_profile() -> Profile:
    return Profile(
        name="Alex Student",
        skills=["Python", "SQL", "Git", "Django", "Docker", "pandas", "REST APIs"],
        years_experience=0.5,
        target_roles=["Software Engineer Intern", "Backend Developer", "Data Analyst"],
        education="B.Tech Computer Science (in progress)",
        summary="Second-year CS student with Python and backend project experience.",
    )


def mock_score(profile: Profile, job: Job) -> tuple[int, str, list[str]]:
    """Fake scoring: count how many profile skills appear in the description."""
    text = f"{job.title} {job.description}".lower()
    matched = [s for s in profile.skills if s.lower() in text]
    score = min(95, 40 + 12 * len(matched))
    return score, f"Mock score: {len(matched)} of your skills appear in this posting.", matched


def mock_cover_letter(profile: Profile, job: Job) -> str:
    skills = ", ".join(profile.skills[:3])
    return (f"Dear Hiring Team,\n\nI am excited to apply for the {job.title} role at "
            f"{job.company}. My background in {skills} fits what you are looking for.\n\n"
            f"(This is a MOCK cover letter - run without --mock to get a real one.)\n\n"
            f"Best regards,\n{profile.name}")
