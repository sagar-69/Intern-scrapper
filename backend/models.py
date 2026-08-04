from datetime import date, datetime
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

class JobLink(BaseModel):
    url: HttpUrl
    title: str
    is_internship: bool = False

class InternshipPosting(BaseModel):
    title: str
    company: str
    location: str = "Not specified"
    description: str = ""
    deadline: date | None = None
    url: HttpUrl
    employment_type: str = "Internship"
    source_target_id: int | None = None

class TargetCreate(BaseModel):
    url: HttpUrl

class Target(BaseModel):
    id: int
    url: HttpUrl
    active: bool
    last_scraped_at: datetime | None = None

class RunSummary(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    targets_total: int = 0
    targets_completed: int = 0
    urls_total: int = 0
    urls_completed: int = 0
    postings_found: int = 0
    new_count: int = 0
    updated_count: int = 0
    logs: list[dict] = Field(default_factory=list)

