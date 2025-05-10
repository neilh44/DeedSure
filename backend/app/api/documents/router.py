from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from typing import List, Dict, Any
import uuid
from datetime import datetime
import io
import logging
from app.core.database import get_db
from app.services.document_processor import DocumentProcessor


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)  # Create a logger instance

router = APIRouter()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    try:
        logger.info(f"Starting upload for file: {file.filename}")
        
        # Get file content
        contents = await file.read()
        file_size = len(contents)
        
        # Generate a unique ID
        document_id = str(uuid.uuid4())
        
        # Create a simpler path structure for now: document_id/filename
        safe_filename = "".join([c if c.isalnum() or c in ['.', '-', '_'] else '_' for c in file.filename])
        storage_path = f"{document_id}/{safe_filename}"
        
        # Get Supabase client
        supabase = get_db()
        
        # Skip the test for now and directly try to upload
        try:
            # Convert the bytes to a file-like object
            file_obj = io.BytesIO(contents)
            file_obj.seek(0)  # Ensure we're at the start of the file
            
            # Upload directly - fix the file_options parameter
            storage_response = supabase.storage.from_("deedsure").upload(
                path=storage_path,
                file=file_obj,
                file_options={"content_type": file.content_type}
            )
            
            logger.info(f"File uploaded successfully: {storage_response}")
            
            # Get the file URL
            try:
                storage_url = supabase.storage.from_("deedsure").get_public_url(storage_path)
                logger.info(f"File URL: {storage_url}")
            except Exception as url_error:
                logger.error(f"Error getting URL: {str(url_error)}")
                storage_url = None
        except Exception as storage_error:
            logger.error(f"Storage error: {str(storage_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Storage error: {str(storage_error)}"
            )
        
        # Process document if it's a PDF
        extracted_text = ""
        metadata = {}
        category = "unknown"
        
        if file.content_type == "application/pdf":
            try:
                # Initialize document processor
                doc_processor = DocumentProcessor()
                
                # Extract text from PDF
                extracted_text = await doc_processor.extract_text_from_pdf(contents)
                
                # Categorize and extract metadata if we got text
                if extracted_text:
                    category = await doc_processor.categorize_document(extracted_text)
                    metadata = await doc_processor.extract_metadata(extracted_text, category)
            except Exception as processing_error:
                logger.error(f"Processing error: {str(processing_error)}")
                # Don't fail the upload, just note the processing error
        
        # Temporary hard-coded user ID for development
        current_user_id = "00000000-0000-0000-0000-000000000000"  # Replace with real auth later
        
        # Now create the document record in the database
        try:
            # Prepare document record
            doc_record = {
                "id": document_id,
                "user_id": current_user_id,
                "filename": file.filename,
                "storage_path": storage_path,
                "content_type": file.content_type,
                "size": file_size,
                "category": category,
                "status": "processed" if extracted_text else "uploaded",
                "extracted_text": extracted_text,
                "metadata": metadata
            }
            
            # Insert document record
            db_response = supabase.table("documents").insert(doc_record).execute()
            logger.info(f"Document record created in database")
        except Exception as db_error:
            logger.error(f"Database error: {str(db_error)}")
            # Try to clean up the uploaded file
            try:
                supabase.storage.from_("deedsure").remove([storage_path])
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up file: {str(cleanup_error)}")
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(db_error)}"
            )
        
        return {
            "id": document_id,
            "filename": file.filename,
            "content_type": file.content_type,
            "size": file_size,
            "category": category,
            "status": "processed" if extracted_text else "uploaded",
            "storage_url": storage_url,
            "message": "File uploaded and processed successfully"
        }
        
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading document: {str(e)}"
        )