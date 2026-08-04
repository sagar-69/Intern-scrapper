import asyncio
from scraper import extract
from settings import settings

async def process_links(links, target_id, db, run_id):
    queue=asyncio.Queue()
    for link in links: await queue.put(link)
    counts={"new":0,"updated":0,"completed":0}; lock=asyncio.Lock()
    async def worker(index):
        while True:
            try: link=queue.get_nowait()
            except asyncio.QueueEmpty: return
            try:
                print(f"[SCRAPE] worker-{index} posting_link={link.url} company=discovering", flush=True)
                posting=await extract(link,target_id); is_new=await db.upsert(posting)
                print(f"[SCRAPE] worker-{index} company={posting.company} posting_link={posting.url} status={'new' if is_new else 'updated'}", flush=True)
                async with lock:
                    counts["new" if is_new else "updated"]+=1; counts["completed"]+=1
                    detail=await db.run_detail(run_id); logs=detail.get("logs",[]) if detail else []
                    logs.append({"worker":f"worker-{index}","status":"ok","company":posting.company,"url":str(link.url)})
                    await db.update_run(run_id, urls_completed=counts["completed"], postings_found=counts["completed"], new_count=counts["new"], updated_count=counts["updated"], logs=logs)
            except Exception as exc:
                print(f"[SCRAPE] worker-{index} posting_link={link.url} status=error error={exc}", flush=True)
                async with lock:
                    detail=await db.run_detail(run_id); logs=detail.get("logs",[]) if detail else []
                    logs.append({"worker":f"worker-{index}","status":"error","url":str(link.url),"error":str(exc)})
                    await db.update_run(run_id, urls_completed=counts["completed"], logs=logs)
            finally: queue.task_done()
    await asyncio.gather(*(worker(i+1) for i in range(settings.worker_count)))
    return counts
