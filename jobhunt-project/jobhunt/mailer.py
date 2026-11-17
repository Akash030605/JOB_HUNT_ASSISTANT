"""mailer.py - builds the HTML digest and sends it with SMTP.

SMTP (Simple Mail Transfer Protocol) is how programs send email.
Steps: connect to the mail server -> encrypt -> log in -> send -> disconnect.
Python's standard library (smtplib + email.mime) does all of it.

Gmail tip: you must use an "App Password", not your normal password.
"""

import html
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from jobhunt.models import EnvSettings, ScoredJob


def build_html(scored: list[ScoredJob]) -> str:
    """Turn the list of scored jobs into an HTML string.
    html.escape() protects us from weird characters in job text."""
    esc = html.escape
    cards = []
    for s in scored:
        letter = ""
        if s.cover_letter:
            letter = (f"<p><b>Draft email:</b></p>"
                      f"<pre style='white-space:pre-wrap;font-family:inherit;"
                      f"background:#f6f8fa;padding:10px;border-radius:6px'>"
                      f"{esc(s.cover_letter)}</pre>")
        cards.append(f"""
        <div style="border:1px solid #ddd;border-radius:8px;padding:14px;margin:12px 0">
          <h3 style="margin:0">{esc(s.job.title)} &ndash; {esc(s.job.company)}</h3>
          <p style="margin:4px 0;color:#555">{esc(s.job.location)} &middot;
             <b style="color:#0a7d33">Score {s.score}/100</b></p>
          <p>{esc(s.reasoning)}</p>
          <p><a href="{esc(s.job.url)}">View &amp; apply</a></p>
          {letter}
        </div>""")
    body = "".join(cards) or "<p>No new matching jobs today.</p>"
    return (f"<html><body style='font-family:Arial,sans-serif;max-width:700px'>"
            f"<h2>Your Job Digest &ndash; {date.today():%d %b %Y}</h2>{body}"
            f"</body></html>")


def send_email(env: EnvSettings, scored: list[ScoredJob]) -> None:
    """Send the digest. Raises an exception on failure (the CLI catches it)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Digest: {len(scored)} new match(es)"
    msg["From"] = env.email_from
    msg["To"] = env.email_to

    # Plain-text fallback first, HTML last (email clients show the last one).
    plain = "\n".join(f"{s.score}  {s.job.title} @ {s.job.company}  {s.job.url}"
                      for s in scored) or "No new matching jobs today."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(build_html(scored), "html"))

    if env.smtp_port == 465:  # implicit SSL
        server = smtplib.SMTP_SSL(env.smtp_host, env.smtp_port, timeout=30)
    else:                     # usual case: port 587 + STARTTLS
        server = smtplib.SMTP(env.smtp_host, env.smtp_port, timeout=30)
        server.starttls()
    try:
        server.login(env.smtp_user, env.smtp_password)
        server.sendmail(env.email_from, [env.email_to], msg.as_string())
    finally:
        server.quit()
