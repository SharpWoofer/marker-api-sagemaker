import argparse
import uvicorn
import logging
import os
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from celery.exceptions import TimeoutError
from fastapi.middleware.cors import CORSMiddleware
from marker_api.celery_worker import celery_app
from marker_api.utils import print_markerapi_text_art
from marker.logger import configure_logging
from marker_api.celery_routes import (
    celery_convert_pdf,
    celery_result,
    celery_convert_pdf_concurrent_await,
    celery_convert_pdf_sync,
    celery_batch_convert,
    celery_batch_result,
)
# import gradio as gr
# from marker_api.demo import demo_ui
from marker_api.model.schema import (
    BatchConversionResponse,
    BatchResultResponse,
    CeleryResultResponse,
    CeleryTaskResponse,
    ConversionResponse,
    HealthResponse,
    ServerType,
)
from typing import List

# Initialize logging
configure_logging()
logger = logging.getLogger(__name__)

# Add this after your imports
import os
import asyncio  # Add this import for the async sleep

# Get Redis connection details from environment variables with flexible fallbacks
REDIS_HOST = os.environ.get('REDIS_HOST', 'service-redis-084qf-health')
REDIS_PORT = os.environ.get('REDIS_PORT', '3000')

# Try multiple possible service names for Redis
def get_working_broker_url():
    """Try multiple possible Redis service names"""
    possible_hosts = [
        REDIS_HOST,
        'service-redis-084qf-health',
        'redis',
        'redis.platform-service.svc.cluster.local',
        'service-redis-084qf-health.platform-service.svc.cluster.local'
    ]
    
    for host in possible_hosts:
        broker_url = f"redis://{host}:{REDIS_PORT}/0"
        try:
            # Try to connect to this Redis
            import redis
            r = redis.Redis.from_url(broker_url, socket_connect_timeout=2)
            if r.ping():
                logger.info(f"Successfully connected to Redis at {host}")
                return broker_url
        except Exception as e:
            logger.info(f"Failed to connect to Redis at {host}: {e}")
    
    # Default fallback
    return f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

# Set this as your broker URL - these will be used when celery_app is imported
os.environ['CELERY_BROKER_URL'] = get_working_broker_url()
os.environ['CELERY_RESULT_BACKEND'] = os.environ['CELERY_BROKER_URL']

# Define the base URL with health suffix
APP_SUFFIX = os.environ.get("APP_SUFFIX", "health")
BASE_URL = f"/qsynthesis/container/marker-api-distributed-lnk3f-{APP_SUFFIX}"
logger.info(f"Setting up application with base URL: {BASE_URL}")

# Global variable to hold model list
app = FastAPI(root_path=BASE_URL)

logger.info("Configuring CORS middleware")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Background task to reconnect to Celery workers
async def reconnect_celery_workers():
    """Periodically check and reconnect to Celery workers"""
    logger.info("Starting Celery worker reconnection task")
    
    while True:
        try:
            # Check for active workers
            i = celery_app.control.inspect()
            workers = i.ping() or {}
            
            if workers:
                logger.info(f"Active Celery workers: {list(workers.keys())}")
            else:
                logger.warning("No active Celery workers, attempting reconnection...")
                # Force celery to reconnect to broker
                celery_app.broker_connection().ensure_connection(max_retries=3)
                
        except Exception as e:
            logger.error(f"Error checking Celery workers: {e}")
        
        # Sleep for 30 seconds before checking again
        await asyncio.sleep(30)

def test_redis_connection():
    from marker_api.celery_worker import redis_host, redis_port, broker_url
    logger.info(f"Testing Redis connection to {broker_url}")
    
    try:
        import redis
        # If redis_host is a full URL, extract host and port
        if isinstance(redis_host, str) and redis_host.startswith("redis://"):
            from urllib.parse import urlparse
            parsed_url = urlparse(redis_host)
            actual_host = parsed_url.hostname
            actual_port = parsed_url.port or 6379
        else:
            actual_host = redis_host
            actual_port = int(redis_port)
            
        logger.info(f"Connecting to Redis at {actual_host}:{actual_port}")
        
        # Add connection timeout to avoid hanging if Redis is unreachable
        r = redis.Redis(
            host=actual_host, 
            port=actual_port,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        
        # Perform ping with timeout
        ping_result = r.ping()
        logger.info(f"Redis ping result: {ping_result}")
        return ping_result
    except Exception as e:
        logger.error(f"Redis connection error: {str(e)}")
        # Return False but don't fail the application startup
        return False

@app.on_event("startup")
async def startup_event():
    """Run tasks when the FastAPI app starts up"""
    logger.info("Running FastAPI startup tasks")
    
    # Start Redis connection test
    test_redis_connection()
    
    # Start the worker reconnection task as a background task
    import asyncio
    from fastapi import BackgroundTasks
    
    background_tasks = BackgroundTasks()
    asyncio.create_task(reconnect_celery_workers())
    
    logger.info("Startup tasks scheduled")


# Add Kubernetes health check endpoint
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """
    Main endpoint to display the status of the server and list available functions.
    """
    html_content = """
    <html>
        <head>
            <title>Marker API Server</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    background-color: #f4f4f4;
                    margin: 0;
                    padding: 20px;
                }
                h1 {
                    color: #4CAF50;
                }
                p {
                    font-size: 18px;
                }
                .routes {
                    background-color: #e3e3e3;
                    padding: 10px;
                    border-radius: 8px;
                    margin-top: 20px;
                }
                .route {
                    margin: 5px 0;
                    padding: 5px;
                    font-size: 16px;
                    color: #333;
                }
                .route a {
                    color: #007BFF;
                    text-decoration: none;
                }
                .route a:hover {
                    text-decoration: underline;
                }
            </style>
        </head>
        <body>
            <h1>Welcome to the Marker API Server!</h1>
            <p>The server is running, and here are the available endpoints:</p>
            
            <div class="routes">
                <div class="route">
                    <strong>1. /health</strong> - Get the server status.
                </div>
                <div class="route">
                    <strong>2. /celery/convert</strong> - Convert uploaded documents to markdown.
                </div>
            </div>
            
            <p>Make sure to use the above endpoints for server functionality.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/health", response_model=HealthResponse)
def server():
    """
    Root endpoint to check server status.

    Returns:
    HealthResponse: A welcome message, server type, and number of workers (if distributed).
    """
    worker_count = len(celery_app.control.inspect().stats() or {})
    server_type = ServerType.distributed if worker_count > 0 else ServerType.simple
    return HealthResponse(
        message="Welcome to Marker-api",
        type=server_type,
        workers=worker_count if server_type == ServerType.distributed else None,
    )


# def is_celery_alive() -> bool:
#     logger.debug("Checking if Celery is alive")
#     try:
#         result = celery_app.send_task("celery.ping")
#         result.get(timeout=30)
#         logger.info("Celery is alive")
#         return True
#     except (TimeoutError, Exception) as e:
#         logger.warning(f"Celery is not responding: {str(e)}")
#         return False

def is_celery_alive() -> bool:
    """Check if Celery workers are available using inspection API"""
    logger.debug("Checking if Celery is alive using inspection API")
    try:
        # Use inspect API to find active workers
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        logger.info(f"Active Celery workers: {active_workers}")
        
        if active_workers:
            logger.info("Celery workers found and are active")
            return True
        else:
            logger.warning("No active Celery workers found")
            return False
    except Exception as e:
        logger.warning(f"Error checking Celery workers: {str(e)}")
        return False
    
def check_celery_with_retries(max_retries=3, retry_delay=5):
    """Try to connect to Celery multiple times with delays between attempts"""
    import time
    
    for attempt in range(max_retries):
        logger.info(f"Celery connection attempt {attempt+1}/{max_retries}")
        if is_celery_alive():
            return True
        if attempt < max_retries - 1:
            logger.info(f"Waiting {retry_delay} seconds before retrying...")
            time.sleep(retry_delay)
    
    return False

def test_celery_service_connection():
    """Test direct TCP connection to the Celery worker service"""
    import socket
    
    celery_service = os.environ.get('CELERY_WORKER_SERVICE', 'marker-celery-worker-9v1tr-health')
    celery_port = 8080
    
    logger.info(f"Testing direct connection to {celery_service}:{celery_port}")
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((celery_service, celery_port))
        sock.close()
        
        if result == 0:
            logger.info(f"Successfully connected to {celery_service}:{celery_port}")
            return True
        else:
            logger.warning(f"Could not connect to {celery_service}:{celery_port}, result code: {result}")
            return False
    except Exception as e:
        logger.error(f"Error testing connection to Celery service: {str(e)}")
        return False

def setup_routes(app: FastAPI, celery_live: bool):
    logger.info("Setting up routes")
    if celery_live:
        logger.info("Adding Celery routes")

        @app.post("/convert", response_model=ConversionResponse)
        async def convert_pdf(pdf_file: UploadFile = File(...)):
            return await celery_convert_pdf_concurrent_await(pdf_file)

        @app.post("/celery/convert", response_model=CeleryTaskResponse)
        async def celery_convert(pdf_file: UploadFile = File(...)):
            return await celery_convert_pdf(pdf_file)
        
        @app.post("/celery/convert-sync", response_model=ConversionResponse)
        async def convert_pdf_sync(pdf_file: UploadFile = File(...)):
            return await celery_convert_pdf_sync(pdf_file)

        @app.get("/celery/result/{task_id}", response_model=CeleryResultResponse)
        async def get_celery_result(task_id: str):
            return await celery_result(task_id)

        @app.post("/batch_convert", response_model=BatchConversionResponse)
        async def batch_convert(pdf_files: List[UploadFile] = File(...)):
            return await celery_batch_convert(pdf_files)

        @app.get("/batch_convert/result/{task_id}", response_model=BatchResultResponse)
        async def get_batch_result(task_id: str):
            return await celery_batch_result(task_id)

        logger.info("Adding real-time conversion route")
    else:
        logger.warning("Celery routes not added as Celery is not alive")
    # app = gr.mount_gradio_app(app, demo_ui, path="")


def parse_args():
    logger.debug("Parsing command line arguments")
    parser = argparse.ArgumentParser(description="Run FastAPI with Uvicorn.")
    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="Host to run the FastAPI app"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Port to run the FastAPI app"
    )
    return parser.parse_args()



if __name__ == "__main__":
    args = parse_args()
    print_markerapi_text_art()
    logger.info(f"Starting FastAPI app on {args.host}:{args.port}")
    
    # Test connectivity, but proceed anyway
    celery_alive = check_celery_with_retries(max_retries=2, retry_delay=5)
    if not celery_alive:
        logger.warning("Couldn't connect to Celery, setting up routes anyway")
        celery_alive = True
    
    setup_routes(app, celery_alive)
    
    try:
        # No root_path here - it's already set in the FastAPI app
        uvicorn.run(app, host=args.host, port=args.port)
    except Exception as e:
        logger.critical(f"Failed to start the application: {str(e)}")
        raise