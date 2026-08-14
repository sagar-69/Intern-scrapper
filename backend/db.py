import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import Boolean, Date, DateTime, Integer, JSON, String, Text, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from models import InternshipPosting, JobPosting
from settings import settings


class Base(DeclarativeBase):
    pass


class TargetRow(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PostingRow(Base):
    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False, default="Not specified")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    deadline: Mapped[Any | None] = mapped_column(Date)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    employment_type: Mapped[str] = mapped_column(String(32), nullable=False, default="Full-Time")
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_target_id: Mapped[int | None] = mapped_column(Integer)
    source_site: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    posted_date: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))


class ScrapeRunRow(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    target_url: Mapped[str | None] = mapped_column(Text)
    targets_total: Mapped[int] = mapped_column(Integer, default=0)
    targets_completed: Mapped[int] = mapped_column(Integer, default=0)
    urls_total: Mapped[int] = mapped_column(Integer, default=0)
    urls_completed: Mapped[int] = mapped_column(Integer, default=0)
    postings_found: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    logs: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)


class Database:
    def __init__(self):
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker | None = None

    async def connect(self):
        self.engine = create_async_engine(settings.sqlalchemy_url, future=True)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await self._ensure_runtime_columns()

    async def close(self):
        if self.engine:
            await self.engine.dispose()

    async def _ensure_runtime_columns(self):
        if not self.engine:
            return
        dialect = self.engine.dialect.name
        async with self.engine.begin() as conn:
            if dialect == "postgresql":
                await conn.execute(text("ALTER TABLE postings ADD COLUMN IF NOT EXISTS source_site TEXT NOT NULL DEFAULT ''"))
                await conn.execute(text("ALTER TABLE postings ADD COLUMN IF NOT EXISTS source_url TEXT NOT NULL DEFAULT ''"))
                await conn.execute(text("ALTER TABLE postings ADD COLUMN IF NOT EXISTS posted_date TEXT NOT NULL DEFAULT ''"))
                await conn.execute(text("ALTER TABLE scrape_runs ADD COLUMN IF NOT EXISTS target_url TEXT"))
            elif dialect == "sqlite":
                posting_cols = {row[1] for row in (await conn.execute(text("PRAGMA table_info(postings)"))).all()}
                run_cols = {row[1] for row in (await conn.execute(text("PRAGMA table_info(scrape_runs)"))).all()}
                for column in ("source_site", "source_url", "posted_date"):
                    if column not in posting_cols:
                        await conn.execute(text(f"ALTER TABLE postings ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"))
                if "target_url" not in run_cols:
                    await conn.execute(text("ALTER TABLE scrape_runs ADD COLUMN target_url TEXT"))

    @staticmethod
    def _domain(url: str) -> str:
        netloc = urlparse(url).netloc
        return netloc.removeprefix("www.") if netloc else "unknown"

    @staticmethod
    def _row_dict(row) -> dict:
        data = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        logs = data.get("logs")
        if isinstance(logs, str):
            try:
                data["logs"] = json.loads(logs)
            except json.JSONDecodeError:
                data["logs"] = []
        return data

    @staticmethod
    def _posting_api(row: PostingRow) -> dict:
        return {
            "id": row.id,
            "title": row.title,
            "job_title": row.title,
            "company": row.company,
            "location": row.location,
            "description": row.description,
            "deadline": row.deadline.isoformat() if row.deadline else None,
            "url": row.url,
            "apply_link": row.url,
            "employment_type": row.employment_type,
            "job_type": row.employment_type,
            "source_site": row.source_site,
            "source_url": row.source_url,
            "posted_date": row.posted_date,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    async def targets(self):
        async with self.session_factory() as session:
            rows = (await session.scalars(select(TargetRow).order_by(TargetRow.id.desc()))).all()
            return [self._row_dict(row) for row in rows]

    async def add_target(self, url):
        url = str(url)
        async with self.session_factory() as session:
            existing = await session.scalar(select(TargetRow).where(TargetRow.url == url))
            if existing:
                existing.active = True
                await session.commit()
                await session.refresh(existing)
                return self._row_dict(existing)
            row = TargetRow(url=url, active=True)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._row_dict(row)

    async def toggle_target(self, target_id):
        async with self.session_factory() as session:
            row = await session.get(TargetRow, target_id)
            if not row:
                return None
            row.active = not row.active
            await session.commit()
            await session.refresh(row)
            return self._row_dict(row)

    async def delete_target(self, target_id):
        async with self.session_factory() as session:
            row = await session.get(TargetRow, target_id)
            if row:
                await session.delete(row)
                await session.commit()

    async def mark_target_scraped(self, target_id: int):
        async with self.session_factory() as session:
            row = await session.get(TargetRow, target_id)
            if row:
                row.last_scraped_at = datetime.now(UTC)
                await session.commit()

    async def source_sites(self):
        async with self.session_factory() as session:
            rows = (await session.execute(select(PostingRow.source_site).where(PostingRow.source_site != "").distinct().order_by(PostingRow.source_site))).all()
            return [row[0] for row in rows]

    async def postings(self, search="", location="", deadline="", offset=0, limit=20, job_type="All", source_site=""):
        async with self.session_factory() as session:
            conditions = []
            if search:
                needle = f"%{search}%"
                conditions.append(or_(PostingRow.title.ilike(needle), PostingRow.company.ilike(needle), PostingRow.location.ilike(needle)))
            if location:
                conditions.append(PostingRow.location.ilike(f"%{location}%"))
            if job_type and job_type != "All":
                conditions.append(PostingRow.employment_type == job_type)
            if source_site:
                conditions.append(PostingRow.source_site == source_site)
            if deadline == "active":
                today = datetime.now(UTC).date()
                conditions.append(or_(PostingRow.deadline >= today, PostingRow.deadline.is_(None)))
            elif deadline == "past":
                conditions.append(PostingRow.deadline < datetime.now(UTC).date())

            stmt = select(PostingRow)
            count_stmt = select(func.count()).select_from(PostingRow)
            for condition in conditions:
                stmt = stmt.where(condition)
                count_stmt = count_stmt.where(condition)
            stmt = stmt.order_by(PostingRow.updated_at.desc()).offset(offset).limit(limit)

            rows = (await session.scalars(stmt)).all()
            total = await session.scalar(count_stmt)
            return {"items": [self._posting_api(row) for row in rows], "total": total or 0}

    async def run(self, target_url: str | None = None, targets_total: int = 0):
        async with self.session_factory() as session:
            row = ScrapeRunRow(target_url=target_url, targets_total=targets_total, status="RUNNING")
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return self._row_dict(row)

    async def run_detail(self, run_id):
        async with self.session_factory() as session:
            row = await session.get(ScrapeRunRow, run_id)
            return self._row_dict(row) if row else None

    async def update_run(self, run_id, **values):
        async with self.session_factory() as session:
            row = await session.get(ScrapeRunRow, run_id)
            if not row:
                return
            for key, value in values.items():
                if key == "logs" and isinstance(value, str):
                    value = json.loads(value)
                setattr(row, key, value)
            await session.commit()

    async def append_run_log(self, run_id: int, entry: dict):
        detail = await self.run_detail(run_id)
        if not detail:
            return
        logs = detail.get("logs") or []
        logs.append(entry)
        await self.update_run(run_id, logs=logs)

    async def upsert_job(self, posting: JobPosting, source_target_id: int | None = None) -> bool:
        apply_link = str(posting.apply_link)
        source_url = str(posting.source_url or posting.apply_link)
        source_site = self._domain(source_url)
        raw = f"{posting.job_title.strip().lower()}|{posting.company.strip().lower()}|{apply_link.lower()}"
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()

        async with self.session_factory() as session:
            existing = await session.scalar(select(PostingRow).where(PostingRow.fingerprint == fingerprint))
            if existing:
                existing.title = posting.job_title
                existing.company = posting.company
                existing.location = posting.location
                existing.description = posting.description[:4000]
                existing.url = apply_link
                existing.employment_type = posting.job_type
                existing.source_site = source_site
                existing.source_url = source_url
                existing.posted_date = posting.posted_date or ""
                existing.source_target_id = source_target_id
                existing.updated_at = datetime.now(UTC)
                await session.commit()
                return False

            row = PostingRow(
                title=posting.job_title,
                company=posting.company,
                location=posting.location,
                description=posting.description[:4000],
                deadline=None,
                url=apply_link,
                employment_type=posting.job_type,
                fingerprint=fingerprint,
                source_target_id=source_target_id,
                source_site=source_site,
                source_url=source_url,
                posted_date=posting.posted_date or "",
                updated_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
            return True

    async def upsert(self, posting: InternshipPosting):
        job = JobPosting(
            job_title=posting.title,
            company=posting.company,
            location=posting.location,
            job_type="Internship" if posting.employment_type.lower().startswith("intern") else "Full-Time",
            apply_link=posting.url,
            source_url=posting.url,
            description=posting.description,
        )
        return await self.upsert_job(job, posting.source_target_id)
