# PROJECT.md — Internship Radar

## 1. What this is
An LLM-powered, self-healing web scraper that discovers and extracts internship/early-career job postings from arbitrary company career pages, normalizes them into a strict schema, and serves them through an API + dashboard. It does not rely on brittle CSS/XPath selectors — it renders pages to clean Markdown and lets an LLM semantically map the content, so it survives site redesigns.

## 2. Goals
- Given a list of root domains (`company.com/careers`), automatically discover internship posting URLs.
- Extract structured fields (title, company, location, qualifications, apply link, deadline) from each posting.
- Deduplicate and upsert into Postgres (update if a deadline/field changes, never duplicate).
- Serve results via API + a simple dashboard UI.
- Run the whole pipeline for **zero marginal API cost** using local models where possible, with Google Gemini as the low-cost cloud fallback for higher accuracy passes.

## 3. Non-goals (v1)
- No user accounts / auth / multi-tenant support.
- No email/Slack notification system (planned as a v2 feature — see FEATURE.md).
- No paid proxy/anti-bot bypass infrastructure — basic stealth only.
- No resume-matching or application-autofill features.

## 4. Target user
Solo developer / small team who wants a self-hosted, privacy-respecting internship tracker instead of depending on third-party job boards.

## 5. Stack at a glance
| Layer | Choice | Why |
|---|---|---|
| Scraper | Crawl4AI (open source, async, JS-rendering, HTML→Markdown) | Purpose-built for LLM-ready extraction |
| LLM orchestration | Instructor (open source) | Forces structured, schema-valid output from any LLM backend |
| Cloud LLM | Google Gemini API (`gemini-2.5-flash` / `gemini-2.5-flash-lite`) | Cheapest capable multimodal cloud option, generous free tier |
| Local LLM | Ollama (`qwen2.5:7b` or `llama3.1:8b`) | Zero-cost fallback / privacy mode |
| Schema/validation | Pydantic v2 | Type-safe contracts between LLM output and DB |
| Backend | FastAPI | Async-native, pairs naturally with `asyncio.Queue` workers |
| Queue | `asyncio.Queue` (v1) → Redis/RQ (v2 if scaling beyond single process) | Simplicity first |
| Database | PostgreSQL | Reliable upsert semantics, mature tooling |
| Frontend | React + Vite + Tailwind + shadcn/ui | Open source, fast to build, good defaults |
| Deployment | Docker Compose (Postgres + API + optional Ollama container) | Fully self-hostable |

## 6. Relevant docs in this bundle
- `ARCHITECTURE.md` — full pipeline, schemas, DB design, diagrams.
- `FEATURE.md` — running changelog / feature status tracker (keep this updated as the project evolves — this is the "memory" for future you or an AI coding agent).
- `BUILD_PROMPT.md` — a ready-to-paste master prompt (with wireframes + flowcharts) for an AI coding agent (Claude Code, Cursor, etc.) to scaffold and build the whole thing.
