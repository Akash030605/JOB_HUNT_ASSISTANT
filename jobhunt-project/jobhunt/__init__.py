"""jobhunt - a terminal-based Job Hunt Assistant.

Data flow (this is the story you tell in your presentation):
    Resume PDF -> profile.json -> Fetch ATS jobs -> Prefilter -> Gemini score
    -> Gemini cover letters -> digest.json + terminal table -> SMTP email
"""

__version__ = "1.0.0"
