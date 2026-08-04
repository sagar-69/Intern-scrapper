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
- [x] Extraction stage: Crawl4AI + Instructor (Gemini) → `InternshipPosting`
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
| 2026-08-04 | Implemented LLM scraping (Instructor + Ollama/Gemini), SHA-256 fingerprinting, and deadline filters | Fulfilled MVP requirements defined in FEATURE.md |
| 2026-08-03 | Initial architecture drafted; swapped OpenAI → Google Gemini via Instructor's `from_genai`, added Ollama local fallback | User requested Google API + open-source-first stack |

---

## Known constraints / decisions to remember
- Extraction pass defaults to Gemini (`gemini-2.5-flash-lite`) for field accuracy; Discovery pass defaults to local Ollama to keep link-finding free.
- Dedup key is `sha256(title + company)` — if two identical titles at the same company legitimately differ (e.g. different location), this key will collide. Revisit if that becomes a real case.
- No auth in v1 — this is assumed to run on a private/self-hosted instance only.
