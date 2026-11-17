"""cli.py - the commands the user types. This file is the "conductor":
it doesn't do the hard work itself, it calls the other modules in order.

Commands:
    python -m jobhunt setup
    python -m jobhunt profile --resume resume.pdf
    python -m jobhunt run --limit 10 [--send] [--mock]
"""

import json
import logging
from pathlib import Path

import typer
from pypdf import PdfReader
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import track
from rich.table import Table

from jobhunt import fetcher, llm, mailer, store
from jobhunt.config import (DIGEST_PATH, PROFILE_PATH, ConfigError,
                            load_companies, load_config, load_env)
from jobhunt.models import Profile, ScoredJob
from jobhunt.prefilter import prefilter

app = typer.Typer(help="Job Hunt Assistant - find, score and email jobs from your terminal.",
                  add_completion=False)
console = Console()

# Send log messages (warnings etc.) through Rich so they look nice.
logging.basicConfig(level=logging.WARNING, format="%(message)s", datefmt="[%X]",
                    handlers=[RichHandler(console=console, show_path=False)])
log = logging.getLogger("jobhunt")


def _fail(message: str) -> None:
    """Print a friendly red error and exit (instead of a scary traceback)."""
    console.print(f"[bold red]Error:[/bold red] {message}")
    raise typer.Exit(code=1)


# ---------------------------------------------------------------- setup

@app.command()
def setup() -> None:
    """Interactively create your .env file with API key and email settings."""
    env_path = Path(".env")
    if env_path.exists() and not typer.confirm(".env already exists. Overwrite it?"):
        raise typer.Exit()

    console.print("[bold]Let's set up your secrets.[/bold] (Get a free Gemini key at "
                  "https://aistudio.google.com/apikey)")
    key = typer.prompt("Gemini API key", hide_input=True)
    host = typer.prompt("SMTP host", default="smtp.gmail.com")
    port = typer.prompt("SMTP port", default="587")
    user = typer.prompt("SMTP username (your email)")
    password = typer.prompt("SMTP password / app password", hide_input=True)
    to = typer.prompt("Send digest to", default=user)

    env_path.write_text(
        f"GEMINI_API_KEY={key}\nSMTP_HOST={host}\nSMTP_PORT={port}\n"
        f"SMTP_USER={user}\nSMTP_PASSWORD={password}\n"
        f"EMAIL_FROM={user}\nEMAIL_TO={to}\n", encoding="utf-8")
    console.print("[green]Saved .env.[/green] Next: "
                  "[cyan]python -m jobhunt profile --resume resume.pdf[/cyan]")


# -------------------------------------------------------------- profile

@app.command()
def profile(
    resume: Path = typer.Option(Path("resume.pdf"), help="Path to your PDF resume."),
    mock: bool = typer.Option(False, "--mock", help="Use a fake profile, no API call."),
) -> None:
    """Read your resume PDF, let Gemini extract a profile, save profile.json."""
    try:
        if mock:
            prof = llm.mock_profile()
        else:
            if not resume.exists():
                _fail(f"Resume not found: {resume}")
            env = load_env(need_gemini=True)
            # Step 1: PDF -> plain text
            reader = PdfReader(str(resume))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            if len(text.strip()) < 50:
                _fail("Could not read text from the PDF (is it a scanned image?).")
            # Step 2: text -> structured profile (Gemini)
            with console.status("Asking Gemini to read your resume..."):
                prof = llm.GeminiClient(env.gemini_api_key,
                                        load_config().gemini_model).parse_resume(text)
    except ConfigError as e:
        _fail(str(e))
    except llm.LLMError as e:
        _fail(f"Gemini problem: {e}")

    PROFILE_PATH.write_text(json.dumps(prof.to_dict(), indent=2), encoding="utf-8")

    table = Table(title="Your Profile", show_header=False)
    table.add_row("Name", prof.name)
    table.add_row("Skills", ", ".join(prof.skills))
    table.add_row("Experience", f"{prof.years_experience} years")
    table.add_row("Target roles", ", ".join(prof.target_roles))
    table.add_row("Education", prof.education)
    table.add_row("Summary", prof.summary)
    console.print(table)
    console.print(f"[green]Saved to {PROFILE_PATH}[/green]")


# ------------------------------------------------------------------ run

def _load_profile() -> Profile:
    if not PROFILE_PATH.exists():
        raise ConfigError("profile.json not found. Run `python -m jobhunt profile` first.")
    try:
        return Profile(**json.loads(PROFILE_PATH.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError):
        raise ConfigError("profile.json is damaged. Re-run the profile command.")


def _print_table(scored: list[ScoredJob]) -> None:
    table = Table(title="Matching Jobs", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Score", justify="right")
    table.add_column("Company")
    table.add_column("Title")
    table.add_column("Location")
    table.add_column("Why it matches", max_width=45)
    for i, s in enumerate(scored, start=1):
        color = "green" if s.score >= 85 else "yellow"
        table.add_row(str(i), f"[{color}]{s.score}[/{color}]", s.job.company,
                      s.job.title, s.job.location, s.reasoning)
    console.print(table)


@app.command()
def run(
    limit: int = typer.Option(10, help="Max jobs to score with Gemini (controls cost)."),
    send: bool = typer.Option(False, "--send", help="Email the digest when done."),
    mock: bool = typer.Option(False, "--mock", help="Fake jobs + fake AI + no email."),
) -> None:
    """Run the full pipeline: fetch -> filter -> dedupe -> score -> draft -> show."""
    try:
        cfg = load_config()
        env = None if mock else load_env(need_gemini=True, need_smtp=send)
        prof = llm.mock_profile() if (mock and not PROFILE_PATH.exists()) else _load_profile()
    except ConfigError as e:
        _fail(str(e))

    if mock:
        console.print(Panel("MOCK MODE: fake jobs, fake AI, no emails sent.", style="magenta"))
        client = None
    else:
        client = llm.GeminiClient(env.gemini_api_key, cfg.gemini_model)

    # Step 1: Fetch
    try:
        if mock:
            jobs = fetcher.mock_jobs()
        else:
            with console.status("Fetching jobs from company career pages..."):
                jobs = fetcher.fetch_all(load_companies())
    except ConfigError as e:
        _fail(str(e))
    console.print(f"1. Fetched [bold]{len(jobs)}[/bold] jobs")

    # Step 2: Prefilter
    jobs, dropped = prefilter(jobs, cfg)
    console.print(f"2. Prefilter kept [bold]{len(jobs)}[/bold] "
                  f"(dropped: {dropped['title']} title, {dropped['location']} location, "
                  f"{dropped['too_old']} too old)")

    # Step 3: Skip jobs we've already seen (not in mock mode, so demos repeat)
    seen = set() if mock else store.load_seen()
    jobs = [j for j in jobs if j.uid not in seen]
    console.print(f"3. [bold]{len(jobs)}[/bold] are new (not in seen.json)")

    # Step 4: Limit, then score with Gemini
    jobs = jobs[:limit]
    scored: list[ScoredJob] = []
    for job in track(jobs, description="4. Scoring with AI...", console=console):
        try:
            if mock:
                score, why, matched = llm.mock_score(prof, job)
            else:
                score, why, matched = client.score_job(prof, job)
            scored.append(ScoredJob(job, score, why, matched))
        except Exception as e:  # one bad job must not crash the run
            log.warning("Could not score '%s' at %s: %s", job.title, job.company, e)

    # Step 5: Keep only good matches, best first
    good = sorted((s for s in scored if s.score >= cfg.score_threshold),
                  key=lambda s: s.score, reverse=True)
    console.print(f"5. [bold]{len(good)}[/bold] jobs scored >= {cfg.score_threshold}")

    # Step 6: Draft cover letters for the top N only (saves money)
    for s in track(good[:cfg.top_n_drafts], description="6. Drafting emails...", console=console):
        try:
            s.cover_letter = (llm.mock_cover_letter(prof, s.job) if mock
                              else client.draft_cover_letter(prof, s.job))
        except Exception as e:
            log.warning("Could not draft letter for '%s': %s", s.job.title, e)

    # Step 7: Save digest + show table
    DIGEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIGEST_PATH.write_text(json.dumps([s.to_dict() for s in good], indent=2), encoding="utf-8")
    if good:
        _print_table(good)
    else:
        console.print("[yellow]No jobs passed the score threshold this time.[/yellow]")
    console.print(f"Saved digest to [cyan]{DIGEST_PATH}[/cyan]")

    # Step 8: Email (optional)
    if send:
        if mock:
            console.print("[magenta]MOCK: skipping the real email.[/magenta]")
        else:
            try:
                with console.status("Sending email..."):
                    mailer.send_email(env, good)
                console.print(f"[green]Email sent to {env.email_to}[/green]")
            except Exception as e:
                _fail(f"Could not send email: {e}")

    # Mark jobs as seen ONLY after a successful send. That way a preview run
    # (without --send) doesn't "use up" your jobs before they reach your inbox.
    if send and not mock:
        store.save_seen(seen | {s.job.uid for s in scored})
