import asyncio
import json
import re
from html import unescape
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pydantic import ValidationError

from llm_client import get_llm_client
from models import InternshipPosting, JobLink, JobPosting, JobPostingBatch, JobType
from settings import settings


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

JOB_HINTS = (
    "job",
    "career",
    "role",
    "opening",
    "intern",
    "internship",
    "engineer",
    "developer",
    "analyst",
    "scientist",
    "apply",
)

INTERNSHIP_HINTS = ("intern", "internship", "co-op", "coop", "student", "trainee")
FULL_TIME_HINTS = ("full-time", "full time", "permanent")


def _domain(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc.removeprefix("www.") if netloc else "Unknown"


def _company_from_domain(url: str) -> str:
    domain = _domain(url).split(":")[0]
    if not domain or domain == "Unknown":
        return "Unknown"
    return domain.split(".")[0].replace("-", " ").title()


def _clean(value: str | None) -> str:
    return " ".join(unescape(str(value or "")).split())


def _matches_type(title: str, job_type: JobType) -> bool:
    haystack = title.lower()
    is_internship = any(hint in haystack for hint in INTERNSHIP_HINTS)
    if job_type == "All":
        return True
    if job_type == "Internship":
        return is_internship
    return not is_internship


def _infer_job_type(text: str) -> str:
    haystack = text.lower()
    if any(hint in haystack for hint in INTERNSHIP_HINTS):
        return "Internship"
    if any(hint in haystack for hint in FULL_TIME_HINTS):
        return "Full-Time"
    return "Full-Time"


def _safe_posting(data: dict, fallback_url: str, source_url: str, job_type: JobType) -> JobPosting | None:
    title = _clean(data.get("title") or data.get("job_title") or data.get("name"))
    if not title or not _matches_type(title, job_type):
        return None

    apply_link = data.get("apply_link") or data.get("url") or data.get("sameAs") or fallback_url
    apply_link = urljoin(source_url, str(apply_link))
    company_value = data.get("company") or data.get("hiringOrganization") or _company_from_domain(source_url)
    if isinstance(company_value, dict):
        company_value = company_value.get("name")

    location_value = data.get("location") or data.get("jobLocation") or "Not specified"
    if isinstance(location_value, list):
        location_value = location_value[0] if location_value else "Not specified"
    if isinstance(location_value, dict):
        address = location_value.get("address") or {}
        if isinstance(address, dict):
            location_value = ", ".join(
                _clean(address.get(key))
                for key in ("addressLocality", "addressRegion", "addressCountry")
                if address.get(key)
            )
        else:
            location_value = location_value.get("name") or "Not specified"

    inferred_type = data.get("job_type") or data.get("employmentType") or _infer_job_type(title)
    if isinstance(inferred_type, list):
        inferred_type = " ".join(str(item) for item in inferred_type)
    normalized_type = "Internship" if "intern" in str(inferred_type).lower() or _infer_job_type(title) == "Internship" else "Full-Time"

    if job_type != "All" and normalized_type != job_type:
        return None

    try:
        return JobPosting(
            job_title=title,
            company=_clean(company_value) or _company_from_domain(source_url),
            location=_clean(location_value) or "Not specified",
            job_type=normalized_type,
            apply_link=apply_link,
            posted_date=_clean(data.get("posted_date") or data.get("datePosted") or data.get("updated_time")),
            source_url=source_url,
            description=_clean(data.get("description"))[:4000],
        )
    except ValidationError:
        return None


async def fetch_static_html(url: str) -> str:
    async with httpx.AsyncClient(timeout=settings.scrape_timeout_seconds, follow_redirects=True, headers=BROWSER_HEADERS) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.text


async def fetch_rendered_html(url: str) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent=BROWSER_HEADERS["User-Agent"],
            viewport={"width": 1440, "height": 1100},
            locale="en-US",
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=settings.scrape_timeout_seconds * 1000)
        await _auto_scroll(page)
        html = await page.content()
        await browser.close()
        return html


async def _auto_scroll(page):
    previous_height = 0
    stable_rounds = 0
    for _ in range(8):
        height = await page.evaluate("document.body.scrollHeight")
        if height == previous_height:
            stable_rounds += 1
        else:
            stable_rounds = 0
        if stable_rounds >= 2:
            break
        previous_height = height
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(900)


def extract_json_ld(html: str, source_url: str, job_type: JobType) -> list[JobPosting]:
    soup = BeautifulSoup(html, "html.parser")
    postings: list[JobPosting] = []
    for script in soup.find_all("script", type=lambda value: value and "ld+json" in value):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _walk_json_ld(payload):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if "JobPosting" not in types:
                continue
            posting = _safe_posting(item, source_url, source_url, job_type)
            if posting:
                postings.append(posting)
    return _dedupe(postings)


def _walk_json_ld(payload) -> Iterable[dict]:
    if isinstance(payload, dict):
        yield payload
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _walk_json_ld(item)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk_json_ld(item)


def extract_link_cards(html: str, source_url: str, job_type: JobType) -> list[JobPosting]:
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    default_company = _company_from_domain(source_url)
    if title_tag:
        title_text = _clean(title_tag.get_text())
        if "|" in title_text:
            default_company = _clean(title_text.split("|")[-1]) or default_company

    postings: list[JobPosting] = []
    for anchor in soup.find_all("a", href=True):
        label = _clean(anchor.get_text(" ", strip=True))
        href = urljoin(source_url, anchor["href"])
        haystack = f"{label} {href}".lower()
        if len(label) < 4 or not any(hint in haystack for hint in JOB_HINTS):
            continue
        if not _matches_type(label, job_type):
            continue

        container = anchor.find_parent(["article", "li", "tr", "div"]) or anchor
        context = _clean(container.get_text(" ", strip=True))
        location = _extract_location(context)
        postings.append(
            JobPosting(
                job_title=label[:180],
                company=default_company,
                location=location,
                job_type=_infer_job_type(f"{label} {context}"),
                apply_link=href,
                posted_date=_extract_posted_date(context),
                source_url=source_url,
                description=context[:1000],
            )
        )
    return _dedupe(postings)


def _extract_location(text_value: str) -> str:
    patterns = [
        r"(?:Location|Place|City)\s*[:\-]\s*([^|•\n]{3,90})",
        r"\b(Remote|Hybrid)\b",
        r"\b([A-Z][A-Za-z .'-]+,\s*(?:[A-Z]{2}|India|USA|UK|United States|Canada|Germany|France))\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text_value)
        if match:
            return _clean(match.group(1))
    return "Not specified"


def _extract_posted_date(text_value: str) -> str | None:
    match = re.search(
        r"(?:Posted|Updated|Date posted)\s*[:\-]?\s*([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2})",
        text_value,
        re.I,
    )
    return _clean(match.group(1)) if match else None


def clean_page_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "img", "iframe"]):
        tag.decompose()
    text_value = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text_value)


async def extract_with_ollama(html: str, source_url: str, job_type: JobType) -> list[JobPosting]:
    if settings.llm_mode not in ("local", "hybrid"):
        return []

    text_value = clean_page_text(html)[: settings.llm_context_chars]
    if len(text_value) < 120:
        return []

    prompt = (
        "Extract job postings from the page text into strict JSON. "
        "Return only postings that are visible in the provided text. "
        "Use job_type exactly as 'Internship' or 'Full-Time'. "
        f"Filter requested: {job_type}. "
        "If apply links are relative or missing, use the source page URL.\n\n"
        f"Source URL: {source_url}\n\n"
        f"Page text:\n{text_value}"
    )

    try:
        client = get_llm_client("local")
        result = await asyncio.to_thread(
            client.chat.completions.create,
            model=settings.ollama_model,
            response_model=JobPostingBatch,
            messages=[
                {"role": "system", "content": "You convert career-page text into schema-valid JSON."},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        print(f"[LLM] source={source_url} status=error error={exc}", flush=True)
        return []

    postings = []
    for posting in result.postings:
        normalized = _safe_posting(posting.model_dump(), str(posting.apply_link), source_url, job_type)
        if normalized:
            postings.append(normalized)
    return _dedupe(postings)


def _dedupe(postings: list[JobPosting]) -> list[JobPosting]:
    out: list[JobPosting] = []
    seen: set[str] = set()
    for posting in postings:
        key = f"{posting.job_title.lower()}|{str(posting.apply_link).lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append(posting)
    return out


def _is_sparse(html: str, postings: list[JobPosting]) -> bool:
    text_value = clean_page_text(html)
    script_count = html.lower().count("<script")
    return len(postings) == 0 and (len(text_value) < 700 or script_count >= 8)


async def scrape_url(url: str, job_type: JobType = "All") -> tuple[list[JobPosting], list[dict]]:
    logs: list[dict] = []

    try:
        static_html = await fetch_static_html(url)
        postings = extract_json_ld(static_html, url, job_type) or extract_link_cards(static_html, url, job_type)
        logs.append({"tier": "static", "status": "ok", "found": len(postings), "url": url})
    except Exception as exc:
        static_html = ""
        postings = []
        logs.append({"tier": "static", "status": "error", "error": str(exc), "url": url})

    if postings and not _is_sparse(static_html, postings):
        return postings, logs

    try:
        rendered_html = await fetch_rendered_html(url)
        rendered_postings = extract_json_ld(rendered_html, url, job_type) or extract_link_cards(rendered_html, url, job_type)
        logs.append({"tier": "playwright", "status": "ok", "found": len(rendered_postings), "url": url})
        if rendered_postings:
            return rendered_postings, logs
    except Exception as exc:
        rendered_html = static_html
        logs.append({"tier": "playwright", "status": "error", "error": str(exc), "url": url})

    llm_postings = await extract_with_ollama(rendered_html or static_html, url, job_type)
    logs.append({"tier": "ollama", "status": "ok", "found": len(llm_postings), "url": url})
    return llm_postings, logs


async def discover(target_url: str) -> list[JobLink]:
    postings, _ = await scrape_url(target_url, "Internship")
    return [JobLink(url=posting.apply_link, title=posting.job_title, is_internship=posting.job_type == "Internship") for posting in postings]


async def extract(link: JobLink, target_id: int) -> InternshipPosting:
    postings, _ = await scrape_url(str(link.url), "All")
    if postings:
        posting = postings[0]
        return InternshipPosting(
            title=posting.job_title,
            company=posting.company,
            location=posting.location,
            description=posting.description,
            url=posting.apply_link,
            employment_type=posting.job_type,
            source_target_id=target_id,
        )
    return InternshipPosting(
        title=link.title or str(link.url),
        company=_company_from_domain(str(link.url)),
        location="Not specified",
        url=link.url,
        employment_type="Internship" if link.is_internship else "Full-Time",
        source_target_id=target_id,
    )
