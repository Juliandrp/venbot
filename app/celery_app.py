from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "venbot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.campaign_monitor",
        "app.workers.shipping_tracker",
        "app.workers.notifications",
        "app.workers.content_pipeline",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="America/Bogota",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.content_pipeline.*": {"queue": "content"},
        "app.workers.notifications.*": {"queue": "notifications"},
        "app.workers.campaign_monitor.*": {"queue": "default"},
        "app.workers.shipping_tracker.*": {"queue": "default"},
    },
    beat_schedule={
        # Monitoreo de campañas de Meta Ads cada 30 minutos
        "monitor-campaigns": {
            "task": "app.workers.campaign_monitor.check_all_campaigns",
            "schedule": crontab(minute="*/30"),
        },
        # Rastreo de envíos Dropi cada 2 horas
        "track-shipments": {
            "task": "app.workers.shipping_tracker.track_all_shipments",
            "schedule": crontab(minute=0, hour="*/2"),
        },
    },
)
