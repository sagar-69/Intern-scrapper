import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from db import Database
from models import TargetCreate
from scraper import discover
from worker_pool import process_links
from settings import settings

db=Database()

# Default seed targets — inserted on first run when the targets table is empty
DEFAULT_SEED_TARGETS = [
    # FAANG / MAANG
    "https://www.metacareers.com/jobs",
    "https://www.amazon.jobs/en/search?category=student-programs",
    "https://jobs.apple.com/en-us/search?team=internships-STDNT-INTRN",
    "https://explore.jobs.netflix.net/careers",
    "https://www.google.com/about/careers/applications/jobs/results?employment_type=INTERN",
    "https://jobs.careers.microsoft.com/global/en/search?lc=India&et=Internship",
    # Other big tech
    "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite",
    "https://careers.adobe.com/us/en/search-results",
    "https://careers.salesforce.com/en/jobs/",
    "https://www.uber.com/global/en/careers/list/",
    "https://www.atlassian.com/company/careers/all-jobs",
    "https://careers.bloomberg.com/students",
    "https://www.goldmansachs.com/careers/students/",
    "https://qualcomm.wd5.myworkdayjobs.com/External",
    # Y Combinator
    "https://www.workatastartup.com/jobs",
    "https://www.ycombinator.com/companies",
    # Startup job aggregators
    "https://wellfound.com/jobs",
    "https://www.linkedin.com/jobs/internship-jobs/",
    "https://internshala.com/internships",
    "https://www.naukri.com/internship-jobs",
    # India-specific
    "https://www.flipkartcareers.com/#!/joblist",
    "https://careers.swiggy.com/",
    "https://www.zomato.com/careers",
]

@asynccontextmanager
async def lifespan(app):
    await db.connect()
    # Seed default targets on first run (empty targets table)
    existing = await db.targets()
    if not existing:
        # Use env var if provided, otherwise fall back to built-in list
        if settings.seed_target_url:
            urls = [u.strip() for u in settings.seed_target_url.split(",") if u.strip()]
        else:
            urls = DEFAULT_SEED_TARGETS
        for url in urls:
            await db.add_target(url)
    yield
    await db.close()
app=FastAPI(title="Internship Radar", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/health")
async def health(): return {"status":"ok"}
@app.get("/api/postings")
async def postings(search: str="", location: str="", deadline: str="", page: int=Query(1,ge=1), limit: int=20): return await db.postings(search,location,deadline,(page-1)*limit,limit)
@app.get("/api/targets")
async def targets(): return await db.targets()
@app.post("/api/targets")
async def add_target(payload: TargetCreate): return await db.add_target(payload.url)
@app.patch("/api/targets/{target_id}/toggle")
async def toggle_target(target_id:int): return await db.toggle_target(target_id)
@app.delete("/api/targets/{target_id}")
async def delete_target(target_id:int): await db.delete_target(target_id); return {"ok":True}
@app.post("/api/runs")
async def start_run():
    run=await db.run(); asyncio.create_task(execute_run(run["id"])); return run
@app.get("/api/runs/{run_id}")
async def run_detail(run_id:int):
    run=await db.run_detail(run_id)
    if not run: raise HTTPException(404,"Run not found")
    return run
async def execute_run(run_id):
    try:
        targets=[t for t in await db.targets() if t["active"]]
        print(f"[SCRAPE] run={run_id} starting targets={len(targets)}", flush=True)
        await db.update_run(run_id,targets_total=len(targets))
        for target in targets:
            print(f"[DISCOVERY] run={run_id} target={target['url']}", flush=True)
            links=await discover(target["url"])
            print(f"[DISCOVERY] run={run_id} found_links={len(links)} target={target['url']}", flush=True)
            await db.update_run(run_id,targets_completed=(targets.index(target)+1),urls_total=len(links))
            await process_links(links,target["id"],db,run_id)
        await db.update_run(run_id,status="COMPLETED",finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
        print(f"[SCRAPE] run={run_id} completed", flush=True)
    except Exception as exc:
        print(f"[SCRAPE] run={run_id} failed error={exc}", flush=True)
        await db.update_run(run_id,status="FAILED",finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),logs=[{"status":"error","error":str(exc)}])
