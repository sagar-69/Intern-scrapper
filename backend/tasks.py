import asyncio
from datetime import UTC, datetime

from celery_app import celery_app
from db import Database
from models import JobType
from scraper import scrape_url


async def _run_single_url(run_id: int, url: str, job_type: JobType, target_id: int | None = None):
    db = Database()
    await db.connect()
    try:
        print(f"[SCRAPE] run={run_id} url={url} job_type={job_type}", flush=True)
        await db.update_run(run_id, status="RUNNING", target_url=url, targets_total=1)
        postings, tier_logs = await scrape_url(url, job_type)
        await db.update_run(run_id, urls_total=len(postings), targets_completed=1)

        new_count = 0
        updated_count = 0
        logs = tier_logs[:]

        for index, posting in enumerate(postings, start=1):
            is_new = await db.upsert_job(posting, source_target_id=target_id)
            new_count += 1 if is_new else 0
            updated_count += 0 if is_new else 1
            logs.append(
                {
                    "tier": "upsert",
                    "status": "ok",
                    "company": posting.company,
                    "title": posting.job_title,
                    "url": str(posting.apply_link),
                    "job_type": posting.job_type,
                }
            )
            print(
                f"[POSTING] run={run_id} company={posting.company} "
                f"title={posting.job_title} link={posting.apply_link} "
                f"status={'new' if is_new else 'updated'}",
                flush=True,
            )
            await db.update_run(
                run_id,
                urls_completed=index,
                postings_found=index,
                new_count=new_count,
                updated_count=updated_count,
                logs=logs,
            )

        if target_id:
            await db.mark_target_scraped(target_id)

        await db.update_run(
            run_id,
            status="COMPLETED",
            finished_at=datetime.now(UTC),
            urls_completed=len(postings),
            postings_found=len(postings),
            new_count=new_count,
            updated_count=updated_count,
            logs=logs,
        )
        print(f"[SCRAPE] run={run_id} completed postings={len(postings)}", flush=True)
    except Exception as exc:
        detail = await db.run_detail(run_id)
        logs = detail.get("logs", []) if detail else []
        logs.append({"tier": "run", "status": "error", "url": url, "error": str(exc)})
        await db.update_run(run_id, status="FAILED", finished_at=datetime.now(UTC), logs=logs)
        print(f"[SCRAPE] run={run_id} failed error={exc}", flush=True)
        raise
    finally:
        await db.close()


@celery_app.task(name="tasks.scrape_single_url")
def scrape_single_url(run_id: int, url: str, job_type: JobType = "All", target_id: int | None = None):
    asyncio.run(_run_single_url(run_id, url, job_type, target_id))


async def _run_target_list(run_id: int, targets: list[dict], job_type: JobType):
    db = Database()
    await db.connect()
    try:
        total_targets = len(targets)
        logs: list[dict] = []
        total_urls = 0
        total_completed = 0
        total_new = 0
        total_updated = 0

        await db.update_run(run_id, status="RUNNING", targets_total=total_targets)
        for target_index, target in enumerate(targets, start=1):
            url = target["url"]
            target_id = target.get("id")
            print(f"[SCRAPE] run={run_id} target={url} job_type={job_type}", flush=True)
            postings, tier_logs = await scrape_url(url, job_type)
            logs.extend(tier_logs)
            total_urls += len(postings)

            for posting in postings:
                is_new = await db.upsert_job(posting, source_target_id=target_id)
                total_completed += 1
                total_new += 1 if is_new else 0
                total_updated += 0 if is_new else 1
                logs.append(
                    {
                        "tier": "upsert",
                        "status": "ok",
                        "company": posting.company,
                        "title": posting.job_title,
                        "url": str(posting.apply_link),
                        "job_type": posting.job_type,
                    }
                )
                print(
                    f"[POSTING] run={run_id} company={posting.company} "
                    f"title={posting.job_title} link={posting.apply_link} "
                    f"status={'new' if is_new else 'updated'}",
                    flush=True,
                )

            if target_id:
                await db.mark_target_scraped(target_id)

            await db.update_run(
                run_id,
                targets_completed=target_index,
                urls_total=total_urls,
                urls_completed=total_completed,
                postings_found=total_completed,
                new_count=total_new,
                updated_count=total_updated,
                logs=logs,
            )

        await db.update_run(
            run_id,
            status="COMPLETED",
            finished_at=datetime.now(UTC),
            logs=logs,
        )
        print(f"[SCRAPE] run={run_id} completed targets={total_targets} postings={total_completed}", flush=True)
    except Exception as exc:
        detail = await db.run_detail(run_id)
        logs = detail.get("logs", []) if detail else []
        logs.append({"tier": "run", "status": "error", "error": str(exc)})
        await db.update_run(run_id, status="FAILED", finished_at=datetime.now(UTC), logs=logs)
        print(f"[SCRAPE] run={run_id} failed error={exc}", flush=True)
        raise
    finally:
        await db.close()


@celery_app.task(name="tasks.scrape_target_list")
def scrape_target_list(run_id: int, targets: list[dict], job_type: JobType = "All"):
    asyncio.run(_run_target_list(run_id, targets, job_type))
