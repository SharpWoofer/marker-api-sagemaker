#!/bin/bash
# docker/flower-entrypoint.sh

# Create a simple health check Flask app
cat > flower_health_check.py << 'EOF'
from flask import Flask, request, redirect, Response
import requests

app = Flask(__name__)

# Keep a dedicated health endpoint for kubernetes probes
@app.route('/health')
@app.route("/qsynthesis/container/marker-api-flower-n2b5z-health/health")
def health():
    return "OK", 200

# Proxy all other paths to Flower
@app.route("/qsynthesis/container/marker-api-flower-n2b5z-health/")
@app.route("/qsynthesis/container/marker-api-flower-n2b5z-health/<path:path>")
@app.route('/')
@app.route('/<path:path>')
def proxy_to_flower(path=""):
    # Forward the request to Flower running on port 5555
    url = f'http://localhost:5555/{path}'
    
    # Include query parameters if any
    if request.query_string:
        url += f'?{request.query_string.decode("utf-8")}'
    
    # Forward the request with the same method and headers
    resp = requests.request(
        method=request.method,
        url=url,
        headers={key: value for key, value in request.headers if key != 'Host'},
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
    
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)
EOF

# Start Flower in the background with internal port 5555
celery -A marker_api.celery_worker.celery_app flower \
  --port=5555 \
  --url_prefix=qsynthesis/container/marker-api-flower-n2b5z-health \
  --address=127.0.0.1 &

# Start the Flask app in the foreground
python flower_health_check.py