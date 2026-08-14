from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator


JobType = Literal["All", "Full-Time", "Internship"]


class JobLink(BaseModel):
    url: HttpUrl
    title: str = ""
    is_internship: bool = False


class JobPosting(BaseModel):
    job_title: str = Field(description="Exact job title")
    company: str = Field(default="Unknown")
    location: str = Field(default="Not specified")
    job_type: Literal["Internship", "Full-Time"] = "Full-Time"
    apply_link: HttpUrl
    posted_date: str | None = None
    source_url: HttpUrl | None = None
    description: str = ""

    @field_validator("job_title", "company", "location", mode="before")
    @classmethod
    def clean_text(cls, value):
        return " ".join(str(value or "").split())


class JobPostingBatch(BaseModel):
    postings: list[JobPosting] = Field(default_factory=list)


class InternshipPosting(BaseModel):
    """Backward-compatible model used by older worker code."""

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

    @field_validator("url", mode="before")
    @classmethod
    def add_scheme(cls, value):
        value = str(value).strip()
        return value if value.startswith(("http://", "https://")) else f"https://{value}"


class ScrapeRequest(BaseModel):
    url: HttpUrl
    job_type: JobType = "All"

    @field_validator("url", mode="before")
    @classmethod
    def normalize_url(cls, value):
        value = str(value).strip()
        return value if value.startswith(("http://", "https://")) else f"https://{value}"


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
    target_url: str | None = None
    targets_total: int = 0
    targets_completed: int = 0
    urls_total: int = 0
    urls_completed: int = 0
    postings_found: int = 0
    new_count: int = 0
    updated_count: int = 0
    logs: list[dict] = Field(default_factory=list)
