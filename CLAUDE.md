Tariff Claim Pilot: a small Flask tool that cleans synthetic road-traffic claim notifications, extracts facts with an LLM, triages them against OIC rules, and drafts claimant updates that a person approves.

What to build: SPEC.md. It is the source of truth. If something isn't in it, ask before building it.
Why and in what order: PROJECT_PLAN.md.

Stack
Python 3.11 · Flask · SQLite · Pydantic · python-docx · pytest · one LLM API (provider and model set in .env) · deployed on Render with gunicorn.

Commands
Install: pip install -r requirements.txt
Generate data: python generate_claims.py
Run locally: flask --app app run --debug
Tests: pytest

Rules
Work on one build step from PROJECT_PLAN.md at a time. Plan first, then build, then run the tests.
Keep it simple. No extra libraries, frameworks or features that aren't in SPEC.md.
Every triage rule and every draft check gets its own unit test.
Every LLM output is validated with Pydantic before it's used.
Every LLM call has a timeout and is logged with its prompt version.
Prompts live in prompts/ as versioned text files (extract_v1.txt, draft_v1.txt). Never hard-code prompt text in Python.
All user-facing text is in British English.
Synthetic data only. Never add real names, addresses, plates or contact details.
Never send pilot_labels.csv to the LLM or use it anywhere except the Results page.
Don't change generate_claims.py or claim_notifications.csv.
Secrets live only in .env, which is in .gitignore. Never print, log or commit an API key.
Rate-limit any route that calls the LLM.
Keep functions short and named for what they do, so each one can be explained in a sentence.
- Whenever you add a tool, library or step that creates files (databases, caches, build output, logs, generated documents, local config), add those paths to `.gitignore` in the same change, under the matching heading.
- Never put source code, `SPEC.md`, `project_plan.md`, `CLAUDE.md`, `.env.example`, `requirements.txt`, `claim_notifications.csv` or `pilot_labels.csv` in `.gitignore`.
- Before every commit, run `git status` and confirm no `.env` file, database, log or generated document is staged. If one is, stop and fix `.gitignore` first.