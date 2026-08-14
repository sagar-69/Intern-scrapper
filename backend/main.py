from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from db import Database
from models import JobType, ScrapeRequest, TargetCreate
from settings import settings
from tasks import scrape_single_url, scrape_target_list


db = Database()

DEFAULT_SEED_TARGETS = [
    "https://www.amazon.jobs/en/search?base_query=intern&loc_query=",
    "https://jobs.careers.microsoft.com/global/en/search?et=Internship",
    "https://www.google.com/about/careers/applications/jobs/results?employment_type=INTERN",
]


@asynccontextmanager
async def lifespan(app):
    await db.connect()
    existing = await db.targets()
    if not existing:
        urls = [u.strip() for u in settings.seed_target_url.split(",") if u.strip()] or DEFAULT_SEED_TARGETS
        for url in urls:
            await db.add_target(url)
    yield
    await db.close()


app = FastAPI(title="Universal Scraping Platform", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "system": "Universal Scraping Platform"}


@app.get("/api/postings")
async def postings(
    search: str = "",
    location: str = "",
    deadline: str = "",
    job_type: JobType = "All",
    source_site: str = "",
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    return await db.postings(
        search=search,
        location=location,
        deadline=deadline,
        job_type=job_type,
        source_site=source_site,
        offset=(page - 1) * limit,
        limit=limit,
    )


@app.get("/api/sources")
async def sources():
    return {"items": await db.source_sites()}


@app.get("/api/targets")
async def targets():
    return await db.targets()


@app.post("/api/targets")
async def add_target(payload: TargetCreate):
    return await db.add_target(payload.url)


@app.patch("/api/targets/{target_id}/toggle")
async def toggle_target(target_id: int):
    target = await db.toggle_target(target_id)
    if not target:
        raise HTTPException(404, "Target not found")
    return target


@app.delete("/api/targets/{target_id}")
async def delete_target(target_id: int):
    await db.delete_target(target_id)
    return {"ok": True}


@app.post("/api/scrape")
async def scrape(payload: ScrapeRequest):
    run = await db.run(target_url=str(payload.url), targets_total=1)
    scrape_single_url.delay(run["id"], str(payload.url), payload.job_type, None)
    return run


@app.post("/api/runs")
async def start_run(job_type: JobType = "All"):
    targets = [target for target in await db.targets() if target["active"]]
    run = await db.run(targets_total=len(targets))
    scrape_target_list.delay(run["id"], targets, job_type)
    return run


@app.get("/api/runs/{run_id}")
async def run_detail(run_id: int):
    run = await db.run_detail(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run
