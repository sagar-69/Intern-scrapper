from celery import Celery

from settings import settings


celery_app = Celery(
    "universal_scraper",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
)
