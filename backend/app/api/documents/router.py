from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from typing import List, Dict, Any
import uuid
from datetime import datetime
import logging
# Fix imports based on your project structure
from app.core.database import get_admin_db, get_current_active_user  # Import both from database.py

from app.services.document_processor import DocumentProcessor


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)  # Create a logger instance

router = APIRouter()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_active_user)  # Get authenticated user
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
        
        # Get Supabase admin client to bypass RLS
        supabase = get_admin_db()
        
        # Try to upload the file
        try:
            # Upload directly using the raw bytes
            storage_response = supabase.storage.from_("deedsure").upload(
                path=storage_path,
                file=contents,  # Pass the raw bytes instead of BytesIO
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
        
        # Use the authenticated user's ID
        current_user_id = current_user["id"]
        
        # Now create the document record in the database
        try:
            # Prepare document record with fields that match the database schema
            doc_record = {
                "id": document_id,
                "user_id": current_user_id,  # Use the real authenticated user ID
                "filename": file.filename,
                "file_path": storage_path,  # Using file_path as per DB schema
                "content_type": file.content_type,
                "file_size": file_size,
                "file_size_bytes": file_size,
                "category": category,
                "status": "processed" if extracted_text else "uploaded",
                "extracted_text": extracted_text,
                "metadata": metadata
            }
            
            # Log the document record being inserted
            logger.info(f"Inserting document record with fields: {', '.join(doc_record.keys())}")
            
            # Insert document record using admin client to bypass RLS
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
            "file_size": file_size,
            "file_size_bytes": file_size,
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