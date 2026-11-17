"""store.py - remembers which jobs we already processed (seen.json).

Without this, you'd get the same jobs in your inbox every day.
We store a set of unique job ids (Job.uid) in a JSON file.
"""

import json
import logging
from pathlib import Path

from jobhunt.config import SEEN_PATH

log = logging.getLogger("jobhunt")


def load_seen(path: Path = SEEN_PATH) -> set[str]:
    """Read seen.json. Missing or corrupted file -> start fresh (no crash)."""
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError):
        log.warning("%s is corrupted, starting with an empty list.", path)
        return set()


def save_seen(seen: set[str], path: Path = SEEN_PATH) -> None:
    """Write the set back to disk (sorted so the file is tidy)."""
    path.write_text(json.dumps(sorted(seen), indent=2), encoding="utf-8")
