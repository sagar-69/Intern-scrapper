# ARCHITECTURE.md — Internship Radar

## 1. System overview (ASCII flowchart)

```
                          ┌────────────────────────┐
                          │   Domain Seed List      │
                          │   (Postgres: targets)   │
                          └───────────┬─────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │   STAGE 1 — DISCOVERY (Producer)  │
                    │  Crawl4AI renders root career page │
                    │  → clean Markdown                  │
                    │  → Instructor + Gemini/Ollama       │
                    │    extracts List[JobLink]           │
                    └───────────────┬────────────────────┘
                                    │  is_internship == true
                                    ▼
                    ┌──────────────────────────────────┐
                    │   asyncio.Queue  (scrape_queue)   │
                    │   URL objects pushed here          │
                    └───────────────┬────────────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 ▼                  ▼                  ▼
           ┌───────────┐      ┌───────────┐      ┌───────────┐
           │ Worker 1  │      │ Worker 2  │ ...  │ Worker N  │   (N configurable, default 5)
           └─────┬─────┘      └─────┬─────┘      └─────┬─────┘
                 │                  │                  │
                 ▼                  ▼                  ▼
        ┌────────────────────────────────────────────────────┐
        │   STAGE 2 — EXTRACTION (Consumer)                    │
        │  Crawl4AI visits job URL → Markdown                  │
        │  Instructor + Gemini/Ollama → InternshipPosting obj  │
        │  (pagination links found here get re-queued)         │
        └───────────────────────┬────────────────────────────┘
                                │
                                ▼
        ┌────────────────────────────────────────────────────┐
        │   STAGE 3 — VALIDATE + UPSERT                        │
        │  hash(title + company) → stable id                   │
        │  INSERT ... ON CONFLICT DO UPDATE (Postgres upsert)  │
        └───────────────────────┬────────────────────────────┘
                                │
                                ▼
        ┌────────────────────────────────────────────────────┐
        │   FastAPI  (read layer)                               │
        │   /api/postings  /api/targets  /api/jobs/{run_id}     │
        └───────────────────────┬────────────────────────────┘
                                │
                                ▼
                    ┌──────────────────────────┐
                    │  React Dashboard (SPA)     │
                    └──────────────────────────┘
```

## 2. LLM routing strategy
Instructor is backend-agnostic, so both providers sit behind one interface:

```
                ┌─────────────────────────────┐
                │   get_llm_client(mode)        │
                └───────────────┬───────────────┘
              mode="cloud"      │      mode="local"
                    ▼                       ▼
     instructor.from_genai(         instructor.from_openai(
       genai.Client())               AsyncOpenAI(base_url=
       model="gemini-2.5-flash-lite"  "http://localhost:11434/v1"),
                                       model="phi3:mini")
```
Default: use Ollama `phi3:mini` for both Discovery and Extraction. Gemini remains available as an optional cloud mode. Providers are swappable via `.env` — `LLM_MODE=local|cloud|hybrid`.

## 3. Pydantic schemas

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class JobLink(BaseModel):
    url: str
    is_internship: bool = Field(
        description="True only if the role is for an intern, student, or new grad."
    )

class InternshipPosting(BaseModel):
    title: str = Field(description="Exact job title")
    company: str
    location: Optional[str] = Field(description="City, State, or 'Remote'")
    apply_link: str
    qualifications: List[str] = Field(description="List of required skills")
    deadline: Optional[str] = Field(description="ISO date, or null if not found")
    source_url: str
```

## 4. Extractor (Ollama Phi via Instructor)

```python
import instructor
from google import genai
from crawl4ai import AsyncWebCrawler

client = instructor.from_openai(AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama"))

async def extract_job_data(url: str) -> InternshipPosting:
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        markdown = result.markdown

    job_data = await client.chat.completions.create(
        model="phi3:mini",
        response_model=InternshipPosting,
        messages=[
            {"role": "system", "content": "Extract internship data. If a field is missing, return null."},
            {"role": "user", "content": markdown},
        ],
    )
    job_data.source_url = url
    return job_data
```

## 5. Database schema (Postgres)

```sql
CREATE TABLE targets (
    id SERIAL PRIMARY KEY,
    domain TEXT UNIQUE NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    last_scraped_at TIMESTAMPTZ
);

CREATE TABLE postings (
    id TEXT PRIMARY KEY,              -- sha256(title + company)
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    apply_link TEXT NOT NULL,
    qualifications TEXT[],
    deadline DATE,
    source_url TEXT NOT NULL,
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    last_updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE scrape_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    targets_scraped INT,
    postings_found INT,
    status TEXT DEFAULT 'running'    -- running | success | failed
);
```

Upsert pattern:
```sql
INSERT INTO postings (id, title, company, location, apply_link, qualifications, deadline, source_url)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (id) DO UPDATE SET
    location = EXCLUDED.location,
    apply_link = EXCLUDED.apply_link,
    qualifications = EXCLUDED.qualifications,
    deadline = EXCLUDED.deadline,
    last_updated_at = now();
```

## 6. Worker pool lifecycle
1. `scrape_queue = asyncio.Queue()` created at app startup.
2. `N` workers spawned as background asyncio tasks, each looping on `await queue.get()`.
3. Discovery stage pushes internship URLs in.
4. A worker claims a URL → runs `extract_job_data()` → upserts → calls `queue.task_done()`.
5. If a worker finds a "next page" / pagination link during extraction, it re-queues it immediately.
6. `await queue.join()` in the orchestrator blocks until a full run drains, then marks the `scrape_runs` row as `success`.

## 7. Why this survives site redesigns
The LLM reasons over rendered Markdown semantics ("this looks like a job title / deadline"), not CSS selectors — so a company changing its HTML structure does not break extraction, only a full content restructure would.

## 8. Repo layout
```
internship-radar/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app
│   │   ├── schemas.py           # Pydantic models
│   │   ├── llm_client.py        # get_llm_client(mode)
│   │   ├── discovery.py         # Stage 1
│   │   ├── extractor.py         # Stage 2
│   │   ├── worker_pool.py       # Stage 2/3 orchestration
│   │   ├── db.py                # asyncpg pool + upsert queries
│   │   └── routers/
│   │       ├── postings.py
│   │       └── targets.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/Dashboard.tsx
│   │   ├── pages/Targets.tsx
│   │   ├── pages/RunMonitor.tsx
│   │   └── components/
│   └── package.json
├── docker-compose.yml
├── PROJECT.md
├── ARCHITECTURE.md
└── FEATURE.md
```
