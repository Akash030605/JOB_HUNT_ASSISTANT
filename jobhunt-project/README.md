# Job Hunt Assistant

A command-line tool that reads your resume, checks company career pages for fresh openings, scores each job against your profile with Google Gemini, drafts tailored application emails, and sends you a digest. Everything runs in the terminal. No web UI.

> Built as a learning project: the code is heavily commented and each file has one clear job.

## Features

- **Resume to profile:** extracts skills, experience and target roles from a PDF into `profile.json`
- **Three job-board integrations:** Greenhouse, Lever and Ashby (public JSON endpoints, no scraping)
- **Free prefilter first:** title, location and age checks run before any paid AI call
- **AI match scoring:** Gemini rates each job 0-100 with a one-line reason
- **Draft emails:** tailored cover emails for your top matches
- **No repeats:** `seen.json` remembers jobs you've already been sent
- **Rich terminal output:** progress bars and a results table
- **Email digest:** HTML email over SMTP
- **Mock mode:** run the whole pipeline with fake data and no API keys
- **Fault tolerant:** a broken company page or a failed AI call logs a warning instead of crashing the run

## How it works

```
 resume.pdf --> Gemini --> profile.json
                               |
 companies.yaml --> fetch jobs (Greenhouse / Lever / Ashby)
                               |
                  prefilter (title, location, age)   <- free, no AI
                               |
                  skip jobs already in seen.json
                               |
                  Gemini scores each job (0-100)
                               |
                  Gemini drafts emails for the top few
                               |
            out/digest.json + terminal table + SMTP email
```

## Quick start

Requires Python 3.10+.

```bash
git clone https://github.com/YOUR-USERNAME/jobhunt-assistant.git
cd jobhunt-assistant
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Try it with no keys at all:

```bash
python -m jobhunt run --mock
```

Example output in mock mode (simplified):

```
1. Fetched 7 jobs
2. Prefilter kept 3 (dropped: 2 title, 1 location, 1 too old)
3. 3 are new (not in seen.json)

 #  Score  Company      Title                          Why it matches
 1  88     Acme Cloud   Software Engineer Intern       Mock score: 4 of your skills appear...
 2  88     Pixel Labs   Backend Developer (New Grad)   Mock score: 4 of your skills appear...
 3  76     DataNest     Data Analyst                   Mock score: 3 of your skills appear...
```

## Setup for real use

1. **Secrets.** Run `python -m jobhunt setup`, or copy `.env.example` to `.env` and fill it in.
   - Gemini key: free at https://aistudio.google.com/apikey
   - Gmail: turn on 2-Step Verification, then create an **App Password** at https://myaccount.google.com/apppasswords (your normal password won't work)
2. **Preferences.** Edit `config.yaml` (titles, locations, max age, score threshold, model) and `companies.yaml`.
3. **Profile.** Put your PDF resume in the project root and run:
   ```bash
   python -m jobhunt profile --resume resume.pdf
   ```
   The PDF must contain selectable text (not a scan). Check `profile.json` afterwards and edit it by hand if anything is off.
4. **Run.**
   ```bash
   python -m jobhunt run --limit 5          # preview in the terminal
   python -m jobhunt run --limit 10 --send  # also email the digest
   ```

## Commands

| Command | What it does |
|---|---|
| `python -m jobhunt setup` | Creates `.env` interactively |
| `python -m jobhunt profile --resume resume.pdf` | Resume PDF to `profile.json` |
| `python -m jobhunt profile --mock` | Fake profile, no API call |
| `python -m jobhunt run --limit N` | Fetch, filter, score, draft, show table |
| `python -m jobhunt run --send` | Same, then email the digest |
| `python -m jobhunt run --mock` | Whole pipeline with fake data |

`--limit` caps how many jobs are sent to Gemini for scoring, which controls cost.

Jobs are marked as "seen" only after a successful `--send`, so previewing never uses up your matches.

## Configuration

`config.yaml`:

| Key | Meaning |
|---|---|
| `titles_include` | Job title must contain at least one of these words |
| `titles_exclude` | Job title must contain none of these words |
| `locations` | Location must contain one of these (empty list allows everywhere) |
| `max_age_days` | Ignore postings older than this |
| `score_threshold` | Minimum Gemini score (0-100) to keep a job |
| `top_n_drafts` | How many top jobs get a drafted email |
| `gemini_model` | Model ID, e.g. `gemini-3.5-flash-lite` |

`companies.yaml` lists each company's name, ATS (`greenhouse`, `lever` or `ashby`) and slug (the id in its careers URL). Companies change job boards sometimes. A bad slug just produces a warning.

## Project structure

```
jobhunt/
├── __main__.py   # entry point for `python -m jobhunt`
├── cli.py        # Typer commands: setup, profile, run
├── config.py     # loads config.yaml, companies.yaml, .env
├── models.py     # dataclasses: Job, Profile, ScoredJob, Config
├── fetcher.py    # Greenhouse / Lever / Ashby adapters + mock jobs
├── prefilter.py  # title, location and age filtering
├── llm.py        # Gemini: resume parsing, scoring, cover letters
├── mailer.py     # HTML digest + SMTP sending
└── store.py      # seen.json de-duplication
config.yaml
companies.yaml
.env.example
requirements.txt
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `Resume not found` | Put `resume.pdf` in the folder you run the command from (the project root), or pass the full path |
| `404 ... model is no longer available` | Model names get retired. Update `gemini_model` in `config.yaml` |
| `unexpected model name format` | Use the API ID (lowercase, hyphens, no spaces), not the display name |
| `503 UNAVAILABLE` | Google is temporarily overloaded. The tool skips that job and retries it next run |
| Email "sent" but nothing arrived | Check Spam and All Mail. A run with no jobs above the threshold sends an empty digest |
| Gmail login fails | Use an App Password, not your normal password |

## Privacy and safety

- `.env`, `resume.pdf`, `profile.json`, `seen.json` and `out/` are in `.gitignore`. Never commit them.
- Your resume text and job descriptions are sent to Google's Gemini API. Don't use this tool with a resume you aren't comfortable sharing with that service.
- Draft emails are AI-generated. Read and edit them before sending anything to an employer. This tool does not apply to jobs for you.
- It uses public job-board endpoints. Keep your runs reasonable and don't hammer them.

## Roadmap ideas

- More job boards
- Run daily on a schedule (cron / GitHub Actions)
- Track applied / rejected status
- Unit tests for the prefilter and JSON cleanup

## Contributing

Issues and pull requests are welcome. For larger changes, open an issue first to discuss it.

