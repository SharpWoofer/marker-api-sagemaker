#!/bin/bash
# scripts/flower-entrypoint.sh

# Create a simple health check Flask app
cat > flower_health_check.py << 'EOF'
from flask import Flask, request, redirect, Response
import requests
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BASE_PATH = "/qsynthesis/container/marker-api-flower-n2b5z-health"

# Keep a dedicated health endpoint for kubernetes probes
@app.route(f"{BASE_PATH}")
@app.route(f"{BASE_PATH}/")
@app.route("/")
def health():
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Celery Monitoring</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            h1 {{ color: #333; }}
            a {{ color: #0066cc; text-decoration: none; padding: 8px 16px; background: #f0f0f0; border-radius: 4px; }}
            a:hover {{ background: #e0e0e0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Celery Task Monitoring</h1>
            <p>This service is healthy and running correctly.</p>
            <p><a href="{BASE_PATH}/flower">Access Flower UI</a> to monitor Celery tasks and workers.</p>
        </div>
    </body>
    </html>
    """
    return html, 200

# Proxy requests to the flower path
@app.route(f"{BASE_PATH}/flower", defaults={'path': ''})
@app.route(f"{BASE_PATH}/flower/<path:path>")
def proxy_flower(path):
    logger.info(f"Proxying request to flower with path: {path}")
    
    # Forward the request to Flower running on port 5555
    url = f'http://localhost:5555/{path}'
    
    # Include query parameters if any
    if request.query_string:
        url += f'?{request.query_string.decode("utf-8")}'
    
    logger.info(f"Forwarding to URL: {url}")
    
    try:
        # Forward the request with the same method and headers
        resp = requests.request(
            method=request.method,
            url=url,
            headers={key: value for (key, value) in request.headers if key != 'Host'},
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False)
        
        # Create a Flask response object
        response = Response(resp.content, resp.status_code)
        
        # Pass through relevant headers
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for name, value in resp.raw.headers.items()
                if name.lower() not in excluded_headers]
        for name, value in headers:
            response.headers[name] = value
        
        # Handle redirects from Flower by rewriting the Location header
        if resp.status_code in [301, 302, 303, 307, 308] and 'Location' in resp.headers:
            redirect_location = resp.headers['Location']
            if redirect_location.startswith('/'):
                # Make relative paths absolute
                response.headers['Location'] = f"{BASE_PATH}/flower{redirect_location}"
            logger.info(f"Rewriting redirect from {redirect_location} to {response.headers['Location']}")
        
        return response
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        return f"Error connecting to Flower: {e}", 500

# Catch-all route for other paths
@app.route('/<path:path>')
def catch_all(path):
    logger.info(f"Catch-all received request for path: {path}")
    return redirect(BASE_PATH, code=302)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
EOF

# Start Flower in the background with internal port 5555
celery -A marker_api.celery_worker.celery_app flower \
  --port=5555 \
  --address=127.0.0.1 &

# Start the Flask app in the foreground
python flower_health_check.py