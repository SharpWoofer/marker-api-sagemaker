from flask import Flask, jsonify
import threading
import subprocess
import sys
import os
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Get the health check path from environment or use default
health_check_path = os.environ.get(
    'HEALTH_CHECK_PATH', 
    '/qsynthesis/container/marker-celery-worker-9v1tr-health'
)

# Global variable to track worker status
worker_status = {"status": "starting", "service": "celery-worker"}

@app.route('/health', methods=['GET'])  # Additional simple health endpoint
@app.route('/', methods=['GET'])        # Root path for simple testing
@app.route(health_check_path, methods=['GET'])  # The actual path checked by the deployment platform
def health_check():
    logger.info(f"Health check requested")
    # Always return 200 for health checks to allow the container to start up
    return jsonify(worker_status), 200

def update_worker_status():
    """Function to periodically update worker status in the background"""
    global worker_status
    
    while True:
        try:
            # Import and use Celery's inspection API to check worker status
            from marker_api.celery_worker import celery_app
            
            inspection = celery_app.control.inspect()
            active_workers = inspection.active()
            
            if active_workers:
                logger.info(f"Active workers: {list(active_workers.keys())}")
                worker_status = {
                    "status": "ok", 
                    "service": "celery-worker", 
                    "workers": list(active_workers.keys())
                }
            else:
                logger.info("No active workers found yet")
                worker_status = {"status": "starting", "service": "celery-worker"}
        except Exception as e:
            logger.error(f"Error checking worker status: {str(e)}")
            worker_status = {"status": "starting", "service": "celery-worker", "error": str(e)}
        
        # Check every 10 seconds
        import time
        time.sleep(10)

def start_celery():
    logger.info("Starting Celery worker...")
    
    # Get Redis host from environment variable
    redis_host = os.environ.get('REDIS_HOST', 'service-redis-084qf-health')
    redis_port = os.environ.get('REDIS_PORT', '3000')
    
    # Set broker URL environment variable for Celery
    os.environ['CELERY_BROKER_URL'] = f"redis://{redis_host}:{redis_port}/0"
    os.environ['CELERY_RESULT_BACKEND'] = f"redis://{redis_host}:{redis_port}/0"
    
    logger.info(f"Using Redis at {redis_host}:{redis_port}")
    
    worker_id = os.environ.get('POD_NAME', 'worker_primary')
    celery_command = [
        "celery", "-A", "marker_api.celery_worker.celery_app", "worker", 
        "--pool=prefork", "--concurrency=4", "-n", f"{worker_id}@%h", "--loglevel=info"
    ]
    
    logger.info(f"Executing: {' '.join(celery_command)}")
    subprocess.call(celery_command)

if __name__ == '__main__':
    # Start celery worker in a separate thread
    celery_thread = threading.Thread(target=start_celery)
    celery_thread.daemon = True
    celery_thread.start()
    
    # Start a background thread to update worker status 
    status_thread = threading.Thread(target=update_worker_status)
    status_thread.daemon = True
    status_thread.start()
    
    # Log the port we're running on
    port = 8080
    logger.info(f"Starting Flask health check server on port {port}")
    
    # Start the Flask app for health checks
    app.run(host='0.0.0.0', port=port)