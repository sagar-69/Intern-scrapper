# FEATURE.md — Feature & Change Tracker

> Keep this file updated after every work session. An AI coding agent (or future you) should read this file FIRST to know what already exists before touching code, so context isn't lost between sessions.

## How to use this file
- Move items from `Planned` → `In Progress` → `Done` as you work.
- Every entry should say *what* and *why*, not just a task name.
- Log breaking changes / schema migrations under `Change Log` with a date.

---

## v0.1 — MVP (Done)
- [x] `targets` CRUD API + Postgres table
- [x] Discovery stage: Crawl4AI + Instructor → `List[JobLink]`
- [x] Extraction stage: Crawl4AI + Instructor (Ollama Phi) → `InternshipPosting`
- [x] `asyncio.Queue` worker pool (default N=5)
- [x] Upsert logic (`ON CONFLICT DO UPDATE`) keyed on `sha256(title+company)`
- [x] `/api/postings` (list, filter by company/location/deadline)
- [x] `/api/targets` (add/remove/list domains)
- [x] `/api/runs/{id}` (scrape run status)
- [x] React dashboard: postings table + filters
- [x] React admin page: manage target domains, trigger manual run
- [x] Docker Compose: postgres + backend + frontend

## v0.2 — Reliability (Planned)
- [ ] Retry/backoff on Crawl4AI fetch failures
- [ ] Rate limiting per domain (avoid hammering a single career page)
- [ ] `LLM_MODE=local|cloud|hybrid` toggle wired end-to-end
- [ ] Structured logging + per-run summary stored in `scrape_runs`

## v0.3 — Nice to have (Backlog, not started)
- [ ] Email/webhook notification on new posting matching saved filters
- [ ] Deduping across near-duplicate postings (same role, slightly different title)
- [ ] Scheduled runs (cron) instead of manual trigger

---

## Change Log
| Date | Change | Reason |
|---|---|---|
| 2026-08-04 | Added default seed list of 25 tech career sites on first run; set up `.venv` for local backend development; updated `.gitignore` | Make the tool instantly useful on first boot and ease local development. |
| 2026-08-04 | Implemented LLM scraping (Instructor + Ollama/Gemini), SHA-256 fingerprinting, and deadline filters | Fulfilled MVP requirements defined in FEATURE.md |
| 2026-08-11 | Added Ollama extraction mode using Instructor | Allow the full pipeline to run locally without Google Gemini |
| 2026-08-11 | Switched the default local model to Ollama `phi3:mini` and updated architecture docs | Use the requested lightweight local model for discovery and extraction |
| 2026-08-11 | Added local non-Docker startup support with automatic `.env` loading | Run the API and React frontend directly on a developer machine |
| 2026-08-11 | Added LAN access support for the React frontend and API | Allow phones on the same Wi-Fi network to use the dashboard |
| 2026-08-11 | Fixed target creation validation, Enter-key submission, and visible target errors | Make Add Target work with bare domains and expose API failures |
| 2026-08-11 | Added backend URL normalization for target creation | Accept career domains with or without `https://` consistently across UI and API |
| 2026-08-11 | Normalized JSONB run logs to arrays in API responses | Prevent the Run Monitor from crashing to a white screen after starting a scrape |
| 2026-08-04 | Added guarded scrape UI, animated scraping state, and terminal posting logs | Prevent white screens on scrape errors and make active scraping visible in both UI and Docker logs |
| 2026-08-03 | Initial architecture drafted; swapped OpenAI → Google Gemini via Instructor's `from_genai`, added Ollama local fallback | User requested Google API + open-source-first stack |

---

## Known constraints / decisions to remember
- Discovery and extraction default to local Ollama `phi3:mini`; Gemini is optional when `LLM_MODE=cloud` or `hybrid`.
- Dedup key is `sha256(title + company)` — if two identical titles at the same company legitimately differ (e.g. different location), this key will collide. Revisit if that becomes a real case.
- No auth in v1 — this is assumed to run on a private/self-hosted instance only.
