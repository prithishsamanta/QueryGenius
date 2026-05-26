# src/core/celery_app.py
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "querygenius",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.tasks.analysis_task"],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Retry behaviour
    task_acks_late=True,           # Only ack after task completes — prevents loss if worker crashes
    task_reject_on_worker_lost=True,

    # Result expiry — keep task results in Redis for 24 hours
    result_expires=86400,

    # Timezone
    timezone="UTC",
    enable_utc=True,
)
