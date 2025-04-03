import os
from celery import Celery
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get Redis host
redis_host = os.environ.get('REDIS_HOST', 'service-redis-084qf-health')
redis_port = os.environ.get('REDIS_PORT', '3000')

logger.info(f"Connecting to Redis at {redis_host}:{redis_port}")

broker_url = f"redis://{redis_host}:{redis_port}/0"
backend_url = f"redis://{redis_host}:{redis_port}/0"

logger.info(f"Broker URL: {broker_url}")

celery_app = Celery(
    "celery_app",
    broker=broker_url,
    backend=backend_url,
    include=["marker_api.celery_tasks"],
)

@celery_app.task(name="celery.ping")
def ping():
    logger.info("Ping task received!")
    return "pong"