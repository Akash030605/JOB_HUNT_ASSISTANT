"""fetcher.py - downloads job postings from company career boards.

ATS = Applicant Tracking System. Greenhouse, Lever and Ashby are three popular
ones, and each has a free public JSON endpoint. Each returns a different shape
of JSON, so we write one small "adapter" per ATS that converts it into our own
Job object (see models.py). After that, the rest of the program doesn't care
where a job came from.

Error handling idea: one broken company must NEVER stop the whole run.
"""

import html
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from jobhunt.models import Company, Job

log = logging.getLogger("jobhunt")
TIMEOUT = 15  # seconds to wait before giving up on a website


# ---------- small helpers ----------

def _strip_html(text: str) -> str:
    """Turn '<p>Hello &amp; welcome</p>' into 'Hello & welcome'."""
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)      # remove tags
    return re.sub(r"\s+", " ", text).strip()  # collapse whitespace


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse '2024-05-01T10:00:00Z' into an aware UTC datetime (or None)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------- one adapter per ATS ----------

def _fetch_greenhouse(company: Company) -> list[Job]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{company.slug}/jobs?content=true"
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()  # turns HTTP errors (404, 500) into exceptions
    jobs = []
    for item in resp.json().get("jobs", []):
        jobs.append(Job(
            id=str(item.get("id")),
            title=item.get("title", ""),
            company=company.name,
            location=(item.get("location") or {}).get("name", ""),
            url=item.get("absolute_url", ""),
            description=_strip_html(item.get("content", "")),
            source="greenhouse",
            posted_at=_parse_iso(item.get("updated_at")),
        ))
    return jobs


def _fetch_lever(company: Company) -> list[Job]:
    url = f"https://api.lever.co/v0/postings/{company.slug}?mode=json"
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = []
    for item in resp.json():
        created_ms = item.get("createdAt")  # Lever uses milliseconds since 1970
        posted = (datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc)
                  if created_ms else None)
        jobs.append(Job(
            id=str(item.get("id")),
            title=item.get("text", ""),
            company=company.name,
            location=(item.get("categories") or {}).get("location", "") or "",
            url=item.get("hostedUrl", ""),
            description=item.get("descriptionPlain", "") or "",
            source="lever",
            posted_at=posted,
        ))
    return jobs


def _fetch_ashby(company: Company) -> list[Job]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{company.slug}"
    resp = requests.get(url, timeout=TIMEOUT)
    resp.raise_for_status()
    jobs = []
    for item in resp.json().get("jobs", []):
        jobs.append(Job(
            id=str(item.get("id")),
            title=item.get("title", ""),
            company=company.name,
            location=item.get("location", "") or "",
            url=item.get("jobUrl", ""),
            description=item.get("descriptionPlain", "") or "",
            source="ashby",
            posted_at=_parse_iso(item.get("publishedAt") or item.get("publishedDate")),
        ))
    return jobs


# Dictionary lookup instead of a long if/elif chain: easy to extend later.
_ADAPTERS = {
    "greenhouse": _fetch_greenhouse,
    "lever": _fetch_lever,
    "ashby": _fetch_ashby,
}


# ---------- public functions ----------

def fetch_all(companies: list[Company]) -> list[Job]:
    """Fetch jobs for every company. Failures are logged, not raised."""
    all_jobs: list[Job] = []
    for company in companies:
        adapter = _ADAPTERS.get(company.ats)
        if adapter is None:
            log.warning("Skipping %s: unknown ATS '%s'", company.name, company.ats)
            continue
        try:
            jobs = adapter(company)
            log.info("Fetched %d jobs from %s", len(jobs), company.name)
            all_jobs.extend(jobs)
        except Exception as e:  # network down, 404 bad slug, bad JSON...
            log.warning("Could not fetch %s (%s): %s", company.name, company.ats, e)
    return all_jobs


def mock_jobs() -> list[Job]:
    """Hardcoded fake jobs for --mock. Some are meant to be filtered out, so
    students can SEE the prefilter working (wrong title, location, too old)."""
    now = datetime.now(timezone.utc)

    def make(i, title, company, location, days_old, desc):
        return Job(id=str(i), title=title, company=company, location=location,
                   url=f"https://example.com/jobs/{i}", description=desc,
                   source="mock", posted_at=now - timedelta(days=days_old))

    return [
        make(1, "Software Engineer Intern", "Acme Cloud", "Remote", 2,
             "Build backend services in Python and SQL. Work with REST APIs and Git."),
        make(2, "Backend Developer (New Grad)", "Pixel Labs", "Bengaluru, India", 5,
             "Python, Django, PostgreSQL and Docker. Great for recent graduates."),
        make(3, "Data Analyst", "DataNest", "India", 7,
             "Use SQL and Python (pandas) to build dashboards and reports."),
        make(4, "Senior Staff Engineer", "BigCorp", "Remote", 1,
             "10+ years of experience leading large distributed systems."),
        make(5, "Software Engineer", "Berlin Works", "Berlin, Germany", 3,
             "Java and Kubernetes. On-site in Berlin."),
        make(6, "Marketing Manager", "BrandCo", "Remote", 4,
             "Plan campaigns and manage social media."),
        make(7, "Frontend Developer", "ShopSwift", "Remote", 60,
             "React and JavaScript. This posting is old on purpose."),
    ]
