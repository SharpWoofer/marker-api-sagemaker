import os
import asyncio
import argparse
import tempfile
from fastapi import FastAPI, Form, Query, UploadFile, File, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional
import traceback
from pathlib import Path
import uuid
import concurrent.futures
from marker.logger import configure_logging  # Import logging configuration
# from marker.models import load_all_models  # Import function to load models
from marker_api.routes import (
    process_document,
)
from marker_api.utils import print_markerapi_text_art
from contextlib import asynccontextmanager
import logging
# import gradio as gr
from marker_api.model.schema import (
    BatchConversionResponse,
    ConversionResponse,
    HealthResponse,
    ServerType,
)
# from marker_api.demo import demo_ui
from marker_api.routes import process_document
from dotenv import load_dotenv


# Initialize logging
configure_logging()
logger = logging.getLogger(__name__)

# Global variable to hold model list
# model_list = None


# Event that runs on startup to load all models
@asynccontextmanager
async def lifespan(app: FastAPI):
    # global model_list
    logger.debug("--------------------- Loading OCR Model -----------------------")
    print_markerapi_text_art()
    # model_list = load_all_models()
    yield

# Initialize FastAPI app
load_dotenv(override=True)
app = FastAPI(lifespan=lifespan, root_path=os.getenv('ROOT_URL_BACKEND'))

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# For genexis deployment:
# @app.get("/qsynthesis/container/marker-api-md8dj-v1", response_model=HealthResponse)
# def root_health_check():
#     """
#     Root endpoint for Kubernetes health checks.
#     """
#     return HealthResponse(message="Marker API is healthy", type=ServerType.simple)

@app.get("/health", response_model=HealthResponse)
def server():
    """
    Root endpoint to check server status.
    """
    return HealthResponse(message="Welcome to Marker-api", type=ServerType.simple)

# Endpoint to convert a single PDF to markdown
@app.post("/convert", response_model=ConversionResponse)
async def convert_document_to_markdown(document_file: UploadFile):
    """
    Endpoint to convert various document types to markdown.
    """
    logger.debug(f"Received file: {document_file.filename}")
    
    # Save uploaded file to a temporary location
    _, file_extension = os.path.splitext(document_file.filename)
    temp_file = tempfile.NamedTemporaryFile(suffix=file_extension, delete=False)
    temp_file_path = temp_file.name
    temp_file.close()
    
    try:
        # Write the uploaded file content to the temporary file
        file_content = await document_file.read()
        with open(temp_file_path, 'wb') as f:
            f.write(file_content)
        
        # Process the document
        markdown_text = await process_document(temp_file_path)
        
        return ConversionResponse(status="Success", result=markdown_text)
        
    except Exception as e:
        logger.error(f"Error processing {document_file.filename}: {str(e)}")
        logger.error(traceback.format_exc())
        return ConversionResponse(status="Error", result=f"Failed to process document: {str(e)}")
        
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)



# # Endpoint to convert multiple PDFs to markdown
# @app.post("/batch_convert", response_model=BatchConversionResponse)
# async def convert_pdfs_to_markdown(file_paths: List[str] = Query(...), are_s3_urls: bool = Query(False)):
#     """
#     Endpoint to convert multiple PDFs to markdown.
    
#     Args:
#         file_paths: List of file paths or S3 URLs
#         are_s3_urls: Whether the provided paths are S3 URLs
#     """
#     logger.debug(f"Received {len(file_paths)} files for batch conversion")
    
#     # Generate a unique task ID
#     task_id = str(uuid.uuid4())
    
#     # Start a background task to process all files
#     # This allows the endpoint to return quickly while processing continues
#     asyncio.create_task(
#         process_batch_files(task_id, file_paths, are_s3_urls)
#     )
    
#     # Return immediately with the task ID
#     return BatchConversionResponse(
#         task_id=task_id,
#         status="Processing"
#     )


# async def process_batch_files(task_id: str, file_paths: List[str], are_s3_urls: bool):
#     """
#     Background task to process multiple files.
    
#     Args:
#         task_id: The unique ID for this batch task
#         file_paths: List of file paths or S3 URLs
#         are_s3_urls: Whether the provided paths are S3 URLs
#     """
#     try:
#         for path in file_paths:
#             temp_path = None
#             try:
#                 if are_s3_urls:
#                     temp_path = await download_from_s3(path)
#                     file_path = Path(temp_path)
#                 else:
#                     file_path = Path(path)
                
#                 # Process the document
#                 await process_document(file_path)
                
#             except Exception as e:
#                 logger.error(f"Error processing {path} in batch {task_id}: {str(e)}")
            
#             finally:
#                 # Clean up temporary file if needed
#                 if temp_path:
#                     import os
#                     if os.path.exists(temp_path):
#                         os.unlink(temp_path)
        
#         # Update task status to completed
#         # Here you would update a database or cache with the task status
#         logger.info(f"Batch task {task_id} completed")
    
#     except Exception as e:
#         logger.error(f"Error in batch task {task_id}: {str(e)}")
#         # Update task status to failed
#         # Here you would update a database or cache with the task status


# --------------------------------------------------- Original Functions ------------------------------


# # Endpoint to convert a single PDF to markdown
# @app.post("/convert", response_model=ConversionResponse)
# async def convert_document_to_markdown(pdf_file: UploadFile):
#     """
#     Endpoint to convert a single PDF to markdown.
#     """
#     logger.debug(f"Received file: {pdf_file.filename}")
#     file = await pdf_file.read()
#     response = process_pdf_file(file, pdf_file.filename, model_list)
#     return ConversionResponse(status="Success", result=response)


# # Endpoint to convert multiple PDFs to markdown
# @app.post("/batch_convert", response_model=BatchConversionResponse)
# async def convert_pdfs_to_markdown(pdf_files: List[UploadFile] = File(...)):
#     """
#     Endpoint to convert multiple PDFs to markdown.
#     """
#     logger.debug(f"Received {len(pdf_files)} files for batch conversion")

#     async def process_files(files):
#         loop = asyncio.get_event_loop()
#         with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
#             coroutines = [
#                 loop.run_in_executor(
#                     pool, process_pdf_file, await file.read(), file.filename, model_list
#                 )
#                 for file in files
#             ]
#             return await asyncio.gather(*coroutines)

#     responses = await process_files(pdf_files)
#     return BatchConversionResponse(results=responses)

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
                    <strong>2. /convert</strong> - Convert uploaded documents to markdown.
                </div>
            </div>
            
            <p>Make sure to use the above endpoints for server functionality.</p>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# Main function to run the server
def main():
    parser = argparse.ArgumentParser(description="Run the marker-api server.")
    parser.add_argument("--host", default="0.0.0.0", help="Host IP address")
    parser.add_argument("--port", type=int, default=8080, help="Port number")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("server:app", host=args.host, port=args.port)


# Entry point to start the server
if __name__ == "__main__":
    main()
