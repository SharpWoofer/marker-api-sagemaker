from celery import Task
from marker_api.celery_worker import celery_app
import io
import logging
import os
import tempfile
from pathlib import Path
import asyncio
from marker_api.utils import process_image_to_base64
from celery.signals import worker_process_init

from server import process_document

logger = logging.getLogger(__name__)


@worker_process_init.connect
def initialize_models(**kwargs):
    print("Worker process initialized")


class PDFConversionTask(Task):
    abstract = True

    def __init__(self):
        super().__init__()

    def __call__(self, *args, **kwargs):
        return self.run(*args, **kwargs)


@celery_app.task(
    ignore_result=False, bind=True, base=PDFConversionTask, name="convert_pdf"
)
def convert_document_to_markdown(self, filename, file_content):
    try:
        # Extract file extension from the filename
        _, file_extension = os.path.splitext(filename)
        
        # Save content to a temporary file
        temp_file = tempfile.NamedTemporaryFile(suffix=file_extension, delete=False)
        temp_file_path = temp_file.name
        temp_file.close()
        
        with open(temp_file_path, 'wb') as f:
            f.write(file_content)
        
        # Process the document using your async function
        markdown_text = asyncio.run(process_document(Path(temp_file_path)))
        
        return {
            "filename": filename,
            "markdown": markdown_text,  # Use a consistent field name
            "status": "ok",
        }
    
    except Exception as e:
        logger.error(f"Error processing {filename}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "filename": filename,
            "status": "Error",
            "error": str(e)
        }
    
    finally:
        # Clean up temporary file
        if 'temp_file_path' in locals() and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


@celery_app.task(
    ignore_result=False, bind=True, base=PDFConversionTask, name="process_batch"
)
def process_batch(self, batch_data):
    results = []
    total = len(batch_data)
    for i, (filename, file_content) in enumerate(batch_data, start=1):
        try:
            # Call the task directly with self
            result = convert_document_to_markdown(self, filename, file_content)
            results.append(result)
        except Exception as e:
            logger.error(f"Error processing {filename}: {str(e)}")
            results.append({"filename": filename, "status": "Error", "error": str(e)})

        # Update progress
        self.update_state(state="PROGRESS", meta={"current": i, "total": total})

    return results