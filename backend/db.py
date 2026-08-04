import json
import asyncpg
from models import InternshipPosting
from settings import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS targets (id SERIAL PRIMARY KEY, url TEXT UNIQUE NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE, last_scraped_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS postings (id SERIAL PRIMARY KEY, title TEXT NOT NULL, company TEXT NOT NULL, location TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', deadline DATE, url TEXT UNIQUE NOT NULL, employment_type TEXT NOT NULL DEFAULT 'Internship', fingerprint TEXT UNIQUE NOT NULL, source_target_id INTEGER REFERENCES targets(id), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
CREATE TABLE IF NOT EXISTS scrape_runs (id SERIAL PRIMARY KEY, status TEXT NOT NULL DEFAULT 'RUNNING', started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), finished_at TIMESTAMPTZ, targets_total INTEGER DEFAULT 0, targets_completed INTEGER DEFAULT 0, urls_total INTEGER DEFAULT 0, urls_completed INTEGER DEFAULT 0, postings_found INTEGER DEFAULT 0, new_count INTEGER DEFAULT 0, updated_count INTEGER DEFAULT 0, logs JSONB NOT NULL DEFAULT '[]');
"""

class Database:
    def __init__(self): self.pool: asyncpg.Pool | None = None
    async def connect(self):
        self.pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10)
        async with self.pool.acquire() as c: await c.execute(SCHEMA)
    async def close(self):
        if self.pool: await self.pool.close()
    async def targets(self):
        rows = await self.pool.fetch("SELECT * FROM targets ORDER BY id DESC")
        return [dict(r) for r in rows]
    async def add_target(self, url):
        return dict(await self.pool.fetchrow("INSERT INTO targets(url) VALUES($1) ON CONFLICT(url) DO UPDATE SET active=TRUE RETURNING *", str(url)))
    async def toggle_target(self, target_id):
        return dict(await self.pool.fetchrow("UPDATE targets SET active=NOT active WHERE id=$1 RETURNING *", target_id))
    async def delete_target(self, target_id): await self.pool.execute("DELETE FROM targets WHERE id=$1", target_id)
    async def postings(self, search="", location="", offset=0, limit=20):
        rows = await self.pool.fetch("SELECT * FROM postings WHERE ($1='' OR title ILIKE '%'||$1||'%' OR company ILIKE '%'||$1||'%') AND ($2='' OR location ILIKE '%'||$2||'%') ORDER BY updated_at DESC OFFSET $3 LIMIT $4", search, location, offset, limit)
        total = await self.pool.fetchval("SELECT COUNT(*) FROM postings WHERE ($1='' OR title ILIKE '%'||$1||'%' OR company ILIKE '%'||$1||'%') AND ($2='' OR location ILIKE '%'||$2||'%')", search, location)
        return {"items":[dict(r) for r in rows], "total":total}
    async def run(self):
        return dict(await self.pool.fetchrow("INSERT INTO scrape_runs DEFAULT VALUES RETURNING *"))
    async def run_detail(self, run_id):
        r = await self.pool.fetchrow("SELECT * FROM scrape_runs WHERE id=$1", run_id)
        return dict(r) if r else None
    async def update_run(self, run_id, **values):
        if not values: return
        if "logs" in values: values["logs"] = json.dumps(values["logs"])
        cols=list(values); args=list(values.values()); sets=", ".join(f"{c}=${i+1}" for i,c in enumerate(cols))
        await self.pool.execute(f"UPDATE scrape_runs SET {sets} WHERE id=${len(args)+1}", *args, run_id)
    async def upsert(self, posting: InternshipPosting):
        fingerprint = f"{posting.title.strip().lower()}::{posting.company.strip().lower()}"
        existing = await self.pool.fetchval("SELECT id FROM postings WHERE fingerprint=$1", fingerprint)
        await self.pool.execute("INSERT INTO postings(title,company,location,description,deadline,url,employment_type,fingerprint,source_target_id) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT(fingerprint) DO UPDATE SET location=EXCLUDED.location,description=EXCLUDED.description,deadline=EXCLUDED.deadline,url=EXCLUDED.url,updated_at=NOW()", posting.title, posting.company, posting.location, posting.description, posting.deadline, str(posting.url), posting.employment_type, fingerprint, posting.source_target_id)
        return existing is None
