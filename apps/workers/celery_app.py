from celery import Celery

from apps.common.settings import settings

broker_url = settings.redis_url
result_backend = settings.redis_url
if settings.celery_task_always_eager:
    broker_url = "memory://"
    result_backend = "cache+memory://"

celery_app = Celery(
    "moviematch",
    broker=broker_url,
    backend=result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_always_eager=settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_store_eager_result=True,
    task_routes={
        "workers.run_collaborative": {"queue": "cf"},
        "workers.run_nlp": {"queue": "nlp"},
        "workers.run_mood": {"queue": "mood"},
    },
)
