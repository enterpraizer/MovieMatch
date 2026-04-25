import os

from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "moviematch",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "workers.tasks.recommendations",
        "workers.tasks.analytics",
    ],
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    broker_connection_retry_on_startup=True,
)

app.conf.beat_schedule = {
    "refresh-embeddings-nightly": {
        "task": "workers.tasks.recommendations.refresh_all_movie_embeddings",
        "schedule": crontab(hour=3, minute=0),
        "options": {"expires": 3600},
    },
    "update-popularity-scores": {
        "task": "workers.tasks.analytics.update_popularity_scores",
        "schedule": crontab(minute=0),
        "options": {"expires": 3500},
    },
    "refresh-movie-avg-ratings": {
        "task": "workers.tasks.analytics.recompute_movie_ratings",
        "schedule": crontab(hour="*/6", minute=15),
        "options": {"expires": 21000},
    },
}
