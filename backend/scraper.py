"""
Scraper module — two-stage pipeline:
  1. Discovery: Crawl4AI → markdown → Instructor+Ollama → List[JobLink]
  2. Extraction: Crawl4AI → markdown → Instructor+Gemini → InternshipPosting

Falls back to heuristic HTML parsing if the LLM call fails.
"""

import asyncio
import re
from datetime import date
from typing import List
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from models import JobLink, InternshipPosting
from settings import settings

# ---------------------------------------------------------------------------
# Instructor client helpers (lazy-initialised)
# ---------------------------------------------------------------------------
_discovery_client = None
_extraction_client = None


def _get_discovery_client():
    """Return an Instructor-wrapped OpenAI client pointing at Ollama."""
    global _discovery_client
    if _discovery_client is None:
        import instructor
        from openai import OpenAI
        _discovery_client = instructor.from_openai(
            OpenAI(base_url=settings.ollama_host, api_key="ollama"),
            mode=instructor.Mode.JSON,
        )
    return _discovery_client


def _get_extraction_client():
    """Return an Instructor-wrapped Gemini client."""
    global _extraction_client
    if _extraction_client is None:
        import instructor
        import google.generativeai as genai
        genai.configure(api_key=settings.gemini_api_key)
        _extraction_client = instructor.from_gemini(
            client=genai.GenerativeModel("gemini-2.5-flash-lite"),
            mode=instructor.Mode.GEMINI_JSON,
        )
    return _extraction_client


# ---------------------------------------------------------------------------
# Page fetching (Crawl4AI preferred, httpx fallback)
# ---------------------------------------------------------------------------
async def fetch_markdown(url: str) -> str:
    """Fetch a page and return its markdown / raw HTML."""
    try:
        from crawl4ai import AsyncWebCrawler
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
            return result.markdown or ""
    except Exception:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            return (await client.get(url)).text


# ---------------------------------------------------------------------------
# Stage 1 — Discovery (Ollama via Instructor)
# ---------------------------------------------------------------------------
# We need a proper Pydantic model wrapper for Instructor to return
from pydantic import BaseModel


class DiscoveredLinks(BaseModel):
    """A list of internship-related links found on a careers page."""
    links: List[JobLink]


async def discover(target_url: str) -> list[JobLink]:
    """
    Crawl a target careers page and extract internship-related links.
    Uses Ollama via Instructor for structured extraction; falls back to
    heuristic HTML parsing on failure.
    """
    raw = await fetch_markdown(target_url)

    # --- Try LLM-based discovery ---
    if settings.llm_mode in ("local", "hybrid"):
        try:
            client = _get_discovery_client()
            prompt = (
                "You are analysing a careers page. Extract ALL links that "
                "point to internship, co-op, or trainee positions.\n\n"
                f"Page content:\n{raw[:8000]}\n\n"
                "Return a JSON object with a 'links' array. Each link must "
                "have 'url' (absolute URL), 'title' (link text), and "
                "'is_internship' (always true for matches)."
            )
            result = await asyncio.to_thread(
                client.chat.completions.create,
                model=settings.ollama_model,
                response_model=DiscoveredLinks,
                messages=[{"role": "user", "content": prompt}],
            )
            if result.links:
                return result.links
        except Exception:
            pass  # fall through to heuristic

    # --- Heuristic fallback (BeautifulSoup) ---
    soup = BeautifulSoup(raw, "html.parser")
    out: list[JobLink] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True) or a["href"]
        href = urljoin(target_url, a["href"])
        text = f"{title} {href}".lower()
        if href not in seen and any(
            kw in text for kw in ("intern", "internship", "co-op", "coop")
        ):
            seen.add(href)
            out.append(JobLink(url=href, title=title, is_internship=True))
    return out


# ---------------------------------------------------------------------------
# Stage 2 — Extraction (Gemini via Instructor)
# ---------------------------------------------------------------------------
async def extract(link: JobLink, target_id: int) -> InternshipPosting:
    """
    Fetch an individual posting page and extract structured fields.
    Uses Gemini via Instructor; falls back to heuristic parsing on failure.
    """
    raw = await fetch_markdown(str(link.url))

    # --- Try LLM-based extraction ---
    if settings.llm_mode in ("cloud", "hybrid") and settings.gemini_api_key:
        try:
            client = _get_extraction_client()
            prompt = (
                "Extract the internship posting details from the following "
                "page content. Return a single JSON object with these fields: "
                "title, company, location, description (max 2000 chars), "
                "deadline (ISO date or null), url, employment_type.\n\n"
                f"Page URL: {link.url}\n"
                f"Link title: {link.title}\n\n"
                f"Page content:\n{raw[:12000]}"
            )
            posting = await asyncio.to_thread(
                client.chat.completions.create,
                response_model=InternshipPosting,
                messages=[{"role": "user", "content": prompt}],
            )
            posting.source_target_id = target_id
            posting.url = link.url  # keep the original URL
            return posting
        except Exception:
            pass  # fall through to heuristic

    # --- Heuristic fallback ---
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(" ", strip=True) if soup.find() else raw
    company = (
        soup.title.get_text(strip=True).split("|")[0] if soup.title else "Company"
    )
    match = re.search(
        r"(?:deadline|apply by|closing date)\s*[:\-]?\s*"
        r"([A-Z][a-z]+ \d{1,2}(?:, \d{4})?)",
        text,
        re.I,
    )
    deadline = None
    if match:
        try:
            raw_date = match.group(1)
            deadline = date.fromisoformat(
                raw_date.replace(", ", "-").replace(" ", "-")
                + ("-2026" if "," not in raw_date else "")
            )
        except ValueError:
            pass

    return InternshipPosting(
        title=link.title,
        company=company[:120],
        location="Remote / See listing",
        description=text[:2000],
        deadline=deadline,
        url=link.url,
        source_target_id=target_id,
    )
