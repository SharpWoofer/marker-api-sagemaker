import os
import time
import base64
from pathlib import Path
import traceback
import logging
from dotenv import load_dotenv
from io import BytesIO
import json
import boto3
import re
import PIL

# Marker imports
from marker.logger import configure_logging
from marker.config.parser import ConfigParser
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
from marker.output import text_from_rendered
from marker.schema.blocks.picture import Picture

# Initialize logging
configure_logging()
logger = logging.getLogger(__name__)

async def process_document(file_path: Path) -> str:
    """Process a PDF document and convert it to markdown"""
    try:
        print("Starting document processing")
        logging.info("Starting document processing")

        load_dotenv()
        
        # Configure marker with settings
        config = {
            "output_format": "markdown",
            "use_llm": True,
            "disable_image_extraction": False,
            "process_images_with_llm": True,
            "llm_service": "marker.services.openrouter.OpenRouterService",
            "aws_access_key_id": os.environ['SAGEMAKER_AWS_ACCESS_KEY_ID'],
            "aws_secret_access_key": os.environ['SAGEMAKER_AWS_SECRET_ACCESS_KEY'],
        }
        
        # Use ConfigParser to handle service initialization
        config_parser = ConfigParser(config)
        llm_service = config_parser.get_llm_service()
        
        # Setup converter with the necessary configuration
        artifact_dict = create_model_dict()
        converter = PdfConverter(
            artifact_dict=artifact_dict, 
            config=config_parser.generate_config_dict(), 
            llm_service=llm_service
        )
        
        # Process the PDF file
        logging.info("Calling the converter function")
        rendered = converter(str(file_path))
        
        # Extract markdown text and images from the rendered output
        markdown_text, _, images = text_from_rendered(rendered)
        
        # Debug the image structure
        logging.info(f"Images type: {type(images)}")
        if images:
            logging.info(f"Images structure: {str(images)[:200]}...")  # Print first 200 chars to see structure
        
        # Post-process to handle images that weren't processed by the LLM
        if "![]" in markdown_text:
            # Find all image references in the markdown
            image_pattern = re.compile(r'!\[\]\(([^)]+\.(jpeg|jpg|png))\)')
            
            # Process each image match
            for match in image_pattern.finditer(markdown_text):
                image_path = match.group(1)
                logging.info(f"Found image reference: {image_path}")
                
                try:
                    # Try to find the image in the images dictionary
                    if image_path in images and isinstance(images[image_path], PIL.Image.Image):
                        img = images[image_path]
                        logging.info(f"Found image for {image_path}, processing with OpenRouter directly")
                        description = await process_image_direct(
                            img,
                            "Describe this image in detail. Focus on both visual elements and any text visible in the image."
                        )
                        
                        # Replace the placeholder with the image plus description
                        # short_alt = "Image: " + description.split(".")[0] # Just use the first sentence for alt text
                        replacement = f"Image ({image_path})\n> Full image description: {description}\n"
                        markdown_text = markdown_text.replace(match.group(0), replacement)
                        logging.info(f"Added description for {image_path}")
                    else:
                        logging.warning(f"Could not find valid image for {image_path}")
                        
                except Exception as e:
                    logging.info(f"Error processing image reference {image_path}: {e}")
                    logging.error(f"Exception details: {traceback.format_exc()}")
        
        return markdown_text

    except Exception as e:
        logging.error(f"Error processing document {file_path}: {str(e)}")
        logging.error(f"Exception details: {traceback.format_exc()}")
        raise

async def process_image_direct(image, prompt):
    """Process an image directly with Sagemaker"""
    try:
        load_dotenv()
        session = boto3.Session(
            aws_access_key_id=os.environ['SAGEMAKER_AWS_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['SAGEMAKER_AWS_SECRET_ACCESS_KEY'],
            region_name='ap-southeast-1'
        )
        
        runtime_client = session.client('sagemaker-runtime')

        # Convert image to base64
        image_bytes = BytesIO()
        image.save(image_bytes, format="JPEG")
        base64_image = base64.b64encode(image_bytes.getvalue()).decode('utf-8')
        
        payload = {
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert image analyst. Describe the image in detail, focusing on both visual elements and any text visible. Be concise but thorough."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
        }
        
        payload_json = json.dumps(payload)
        
        # Call SageMaker endpoint
        response = runtime_client.invoke_endpoint(
            EndpointName='Qwen2-5-VL-72B-Instruct-2025-03-09-10-43-09',
            ContentType='application/json',
            Body=payload_json
        )

        # Parse response
        response_body = response['Body'].read().decode('utf-8')
        output = json.loads(response_body)
        return output["choices"][0]["message"]["content"]
            
    except Exception as e:
        print(f"Error in direct image processing: {str(e)}")
        logging.error(f"Exception details: {traceback.format_exc()}")
        return f"Error processing image: {str(e)}"