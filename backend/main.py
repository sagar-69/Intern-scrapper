import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from db import Database
from models import TargetCreate
from scraper import discover
from worker_pool import process_links

db=Database()
@asynccontextmanager
async def lifespan(app):
    await db.connect(); yield; await db.close()
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
        await db.update_run(run_id,targets_total=len(targets))
        for target in targets:
            links=await discover(target["url"])
            await db.update_run(run_id,targets_completed=(targets.index(target)+1),urls_total=len(links))
            await process_links(links,target["id"],db,run_id)
        await db.update_run(run_id,status="COMPLETED",finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    except Exception as exc:
        await db.update_run(run_id,status="FAILED",finished_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),logs=[{"status":"error","error":str(exc)}])
