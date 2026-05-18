from celery import Celery

from app.core.config import get_settings


settings = get_settings()

celery_app = Celery(
    "iee_copilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.jobs"],
)
