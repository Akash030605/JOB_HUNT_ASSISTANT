"""config.py - loads settings from config.yaml, companies.yaml and .env.

Rule of thumb:
  * config.yaml / companies.yaml -> preferences (safe to share)
  * .env                         -> secrets     (NEVER share or commit)
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from jobhunt.models import Company, Config, EnvSettings

# File locations (relative to the folder you run the command from)
CONFIG_PATH = Path("config.yaml")
COMPANIES_PATH = Path("companies.yaml")
PROFILE_PATH = Path("profile.json")
SEEN_PATH = Path("seen.json")
DIGEST_PATH = Path("out/digest.json")


class ConfigError(Exception):
    """Raised when a setting or file is missing. The CLI shows it nicely."""


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Missing file: {path}. Are you in the project folder?")
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} is not valid YAML: {e}")


def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read config.yaml into a Config object."""
    data = _read_yaml(path)
    return Config(
        # Lower-case everything once here so matching later is simple.
        titles_include=[str(s).lower() for s in data.get("titles_include", [])],
        titles_exclude=[str(s).lower() for s in data.get("titles_exclude", [])],
        locations=[str(s).lower() for s in data.get("locations", [])],
        max_age_days=int(data.get("max_age_days", 14)),
        score_threshold=int(data.get("score_threshold", 70)),
        top_n_drafts=int(data.get("top_n_drafts", 3)),
        gemini_model=str(data.get("gemini_model", "gemini-2.0-flash")),
    )


def load_companies(path: Path = COMPANIES_PATH) -> list[Company]:
    """Read companies.yaml into a list of Company objects."""
    data = _read_yaml(path)
    companies = []
    for item in data.get("companies", []):
        try:
            companies.append(
                Company(name=item["name"], ats=item["ats"].lower(), slug=item["slug"])
            )
        except KeyError as e:
            raise ConfigError(f"A company in {path} is missing the field {e}.")
    return companies


def load_env(need_gemini: bool = True, need_smtp: bool = False) -> EnvSettings:
    """Read secrets from the .env file (or real environment variables)."""
    load_dotenv()  # copies the values in .env into os.environ
    env = EnvSettings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_from=os.getenv("EMAIL_FROM", "") or os.getenv("SMTP_USER", ""),
        email_to=os.getenv("EMAIL_TO", ""),
    )

    # Only complain about the secrets we actually need for this command.
    missing = []
    if need_gemini and not env.gemini_api_key:
        missing.append("GEMINI_API_KEY")
    if need_smtp:
        for name, value in [("SMTP_USER", env.smtp_user),
                            ("SMTP_PASSWORD", env.smtp_password),
                            ("EMAIL_TO", env.email_to)]:
            if not value:
                missing.append(name)
    if missing:
        raise ConfigError(
            "Missing in .env: " + ", ".join(missing)
            + ". Run `python -m jobhunt setup` or try --mock."
        )
    return env
