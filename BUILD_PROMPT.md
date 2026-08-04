# BUILD_PROMPT.md
Paste everything below the line into Claude Code / Cursor / your agent of choice as the first message of a new session.

---

You are building **Internship Radar**, a self-healing, LLM-powered scraper that discovers and extracts internship postings from company career pages and serves them via API + dashboard.

Before writing any code, read `PROJECT.md`, `ARCHITECTURE.md`, and `FEATURE.md` in the repo root — they contain the full context, schema, and current feature status. **Always update `FEATURE.md`** when you finish a task, before moving to the next one, so context survives across sessions.

## Non-negotiable stack
- Scraper: **Crawl4AI** (async, JS-rendering, HTML→Markdown)
- LLM orchestration: **Instructor**
- Cloud LLM: **Google Gemini API** (`gemini-2.5-flash-lite` for extraction) via `instructor.from_genai`
- Local LLM fallback: **Ollama** (`qwen2.5:7b`) via `instructor.from_openai` pointed at Ollama's OpenAI-compatible endpoint
- Validation: **Pydantic v2**
- Backend: **FastAPI** + `asyncpg`
- Queue: **asyncio.Queue** worker pool
- DB: **PostgreSQL**
- Frontend: **React + Vite + Tailwind + shadcn/ui**
- Everything containerized via **Docker Compose**

## Pipeline (implement exactly this flow)

```
targets (Postgres) ──▶ DISCOVERY (Crawl4AI + Instructor) ──▶ List[JobLink]
                                                                    │ is_internship==true
                                                                    ▼
                                                          asyncio.Queue
                                                                    │
                                        ┌───────────────────────────┼───────────────────────────┐
                                        ▼                           ▼                           ▼
                                    Worker 1                    Worker 2      ...            Worker N
                                        │                           │                           │
                                        └───────────────────────────┴───────────────────────────┘
                                                                    ▼
                                       EXTRACTION (Crawl4AI + Instructor + Gemini) ──▶ InternshipPosting
                                                                    │
                                                                    ▼
                                          hash(title+company) ──▶ Postgres UPSERT
                                                                    │
                                                                    ▼
                                                 FastAPI  /api/postings /api/targets /api/runs
                                                                    │
                                                                    ▼
                                                        React Dashboard (SPA)
```

## UI wireframes (build these three screens first)

### Screen 1 — Dashboard (postings table)
```
┌──────────────────────────────────────────────────────────────────────────┐
│  Internship Radar                                    [ + Add Target ]     │
├──────────────────────────────────────────────────────────────────────────┤
│  Search: [_____________]   Location: [Any ▾]   Deadline: [Any ▾]  [Run ▶] │
├──────────────────────────────────────────────────────────────────────────┤
│  TITLE                     COMPANY        LOCATION      DEADLINE   LINK   │
│  ───────────────────────────────────────────────────────────────────────│
│  SWE Intern - Backend      Acme Corp      Remote        Aug 30     [→]   │
│  Data Science Intern       Globex         NYC, NY       Sep 15     [→]   │
│  ML Research Intern        Initech        San Fran, CA  —          [→]   │
│  ...                                                                      │
├──────────────────────────────────────────────────────────────────────────┤
│  ◀ Prev     Page 1 of 6     Next ▶                    124 postings total │
└──────────────────────────────────────────────────────────────────────────┘
```

### Screen 2 — Targets / Admin
```
┌──────────────────────────────────────────────────────────────────────────┐
│  Manage Target Domains                                                    │
├──────────────────────────────────────────────────────────────────────────┤
│  [ https://company.com/careers___________ ]  [ Add Target ]               │
├──────────────────────────────────────────────────────────────────────────┤
│  DOMAIN                        STATUS     LAST SCRAPED     ACTIONS        │
│  ───────────────────────────────────────────────────────────────────────│
│  acme.com/careers              ● active   2h ago           [Pause][Del]   │
│  globex.com/jobs               ● active   6h ago           [Pause][Del]   │
│  initech.com/careers           ○ paused   3d ago           [Resume][Del]  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Screen 3 — Run Monitor (live scrape status)
```
┌──────────────────────────────────────────────────────────────────────────┐
│  Run #42 — started 14:03:12                          status: RUNNING ●   │
├──────────────────────────────────────────────────────────────────────────┤
│  Discovery:   ▓▓▓▓▓▓▓▓▓▓░░░░░░  8 / 14 targets                            │
│  Extraction:  ▓▓▓▓▓░░░░░░░░░░░  22 / 61 URLs   (5 workers active)         │
│  Postings found this run:  22   |   new: 15   updated: 7                  │
├──────────────────────────────────────────────────────────────────────────┤
│  Log                                                                       │
│  14:03:14  worker-2  ✓  acme.com/careers/swe-intern                       │
│  14:03:15  worker-4  ✓  globex.com/jobs/ds-intern                         │
│  14:03:16  worker-1  ✗  initech.com/careers/broken-link (404)             │
└──────────────────────────────────────────────────────────────────────────┘
```

## Build order (respect this sequence; check off in FEATURE.md as you go)
1. Docker Compose skeleton (Postgres + FastAPI stub) — confirm `docker compose up` boots clean.
2. Postgres schema (`targets`, `postings`, `scrape_runs`) from `ARCHITECTURE.md` §5.
3. Pydantic schemas (`JobLink`, `InternshipPosting`) exactly as specified in `ARCHITECTURE.md` §3.
4. `llm_client.py` implementing `get_llm_client(mode: Literal["local","cloud"])` per §2 — read `LLM_MODE` from `.env`, default `hybrid` (local for discovery, cloud for extraction).
5. Discovery stage (`discovery.py`) — Crawl4AI + Instructor, returns internship-only links.
6. `asyncio.Queue` + worker pool (`worker_pool.py`) — default 5 workers, configurable via env.
7. Extraction stage (`extractor.py`) using the Gemini client, exactly the function signature in `ARCHITECTURE.md` §4.
8. Upsert logic (`db.py`) using the SQL in `ARCHITECTURE.md` §5.
9. FastAPI routers: `/api/postings`, `/api/targets`, `/api/runs/{id}`.
10. React frontend: Dashboard → Targets → Run Monitor, in that order, matching the wireframes above.
11. Wire up "Run" button on Dashboard to trigger a scrape run and redirect to Run Monitor.

## Constraints
- Never hardcode an API key — read `GEMINI_API_KEY` and `OLLAMA_HOST` from environment variables, fail fast with a clear error if missing when in the relevant mode.
- All I/O (Crawl4AI, DB, LLM calls) must be async — no blocking calls inside worker coroutines.
- Every new feature or schema change: update `FEATURE.md`'s Change Log with date + reason before considering the task done.
- Match the wireframes' information hierarchy — exact pixel layout is flexible, but every field/column shown above must be present.

## Acceptance criteria for v0.1 (MVP)
- Given at least one seeded target domain, a manual "Run" produces at least one row in `postings` without manual intervention.
- Re-running against the same domain updates existing rows instead of duplicating them.
- Dashboard, Targets, and Run Monitor pages all load real data from the FastAPI backend (no mock data).
- `docker compose up` brings up the entire stack with one command.
