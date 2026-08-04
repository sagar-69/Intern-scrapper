import asyncio, hashlib, re
from datetime import date
from urllib.parse import urljoin
import httpx
from bs4 import BeautifulSoup
from models import JobLink, InternshipPosting

async def fetch_markdown(url: str) -> str:
    try:
        from crawl4ai import AsyncWebCrawler
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
            return result.markdown or ""
    except Exception:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            return (await client.get(url)).text

async def discover(target_url: str) -> list[JobLink]:
    html = await fetch_markdown(target_url)
    soup = BeautifulSoup(html, "html.parser")
    out=[]; seen=set()
    for a in soup.find_all("a", href=True):
        title=a.get_text(" ", strip=True) or a["href"]
        href=urljoin(target_url, a["href"])
        text=f"{title} {href}".lower()
        if href not in seen and any(x in text for x in ("intern", "internship", "co-op", "coop")):
            seen.add(href); out.append(JobLink(url=href, title=title, is_internship=True))
    return out

async def extract(link: JobLink, target_id: int) -> InternshipPosting:
    raw=await fetch_markdown(str(link.url)); soup=BeautifulSoup(raw, "html.parser")
    text=soup.get_text(" ", strip=True) if soup.find() else raw
    company=(soup.title.get_text(strip=True).split("|")[0] if soup.title else "Company")
    match=re.search(r"(?:deadline|apply by|closing date)\s*[:\-]?\s*([A-Z][a-z]+ \d{1,2}(?:, \d{4})?)", text, re.I)
    deadline=None
    if match:
        try: deadline=date.fromisoformat(match.group(1).replace(", ", "-").replace(" ", "-") + ("-2026" if "," not in match.group(1) else ""))
        except ValueError: pass
    return InternshipPosting(title=link.title, company=company[:120], location="Remote / See listing", description=text[:2000], deadline=deadline, url=link.url, source_target_id=target_id)
