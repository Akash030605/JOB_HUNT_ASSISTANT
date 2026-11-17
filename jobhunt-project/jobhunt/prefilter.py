"""prefilter.py - cheap, FREE filtering before we spend Gemini credits.

Order matters: we run the cheapest checks first and throw away as many jobs
as we can. Only the survivors get sent to the (paid) AI for scoring.
"""

from datetime import datetime, timedelta, timezone

from jobhunt.models import Config, Job


def prefilter(jobs: list[Job], cfg: Config) -> tuple[list[Job], dict[str, int]]:
    """Return (jobs_that_passed, counts_of_why_others_were_dropped)."""
    dropped = {"title": 0, "location": 0, "too_old": 0}
    kept: list[Job] = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.max_age_days)

    for job in jobs:
        title = job.title.lower()
        location = job.location.lower()

        # 1. Title must contain at least one "include" word (if any are set)
        if cfg.titles_include and not any(w in title for w in cfg.titles_include):
            dropped["title"] += 1
            continue

        # 2. Title must NOT contain any "exclude" word (e.g. "senior")
        if any(w in title for w in cfg.titles_exclude):
            dropped["title"] += 1
            continue

        # 3. Location must match one of the wanted places (if any are set)
        if cfg.locations and not any(w in location for w in cfg.locations):
            dropped["location"] += 1
            continue

        # 4. Posting must be recent. If the date is unknown we keep the job.
        if job.posted_at is not None and job.posted_at < cutoff:
            dropped["too_old"] += 1
            continue

        kept.append(job)

    return kept, dropped
