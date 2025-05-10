from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from typing import List, Dict, Any
import uuid  # Make sure this is imported
import logging
from app.core.database import get_db, get_admin_db, get_current_active_user
from app.services.document_processor import DocumentProcessor

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    current_user: Dict[str, Any] = Depends(get_current_active_user)
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
        
        # Try to get the admin client first, fall back to regular client
        try:
            supabase = get_admin_db()
            logger.info("Using admin client for database operations")
        except Exception as admin_error:
            logger.warning(f"Could not get admin client: {str(admin_error)}. Falling back to regular client.")
            supabase = get_db()
        
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
            storage_url = supabase.storage.from_("deedsure").get_public_url(storage_path)
            logger.info(f"File URL: {storage_url}")
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
        
        # Handle the user_id properly - ensure it's a UUID if the database expects a UUID
        # Check the type of current_user["id"] and convert if needed
        try:
            # If it's already a UUID object, use it directly
            if isinstance(current_user["id"], uuid.UUID):
                current_user_id = current_user["id"]
            # If it's a string representation of a UUID, convert it
            else:
                current_user_id = uuid.UUID(current_user["id"])
            
            logger.info(f"Using user ID: {current_user_id} (type: {type(current_user_id)})")
        except Exception as uid_error:
            logger.error(f"Error converting user ID: {str(uid_error)}")
            # Fall back to using it as-is
            current_user_id = current_user["id"]
            logger.info(f"Falling back to user ID as-is: {current_user_id} (type: {type(current_user_id)})")
        
        # Now create the document record in the database
        try:
            # Prepare document record with fields that match the database schema
            doc_record = {
                "id": document_id,
                "user_id": current_user_id,  # This should now be the correct type (UUID)
                "filename": file.filename,
                "file_path": storage_path,
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
            logger.info(f"user_id type: {type(doc_record['user_id'])}")
            
            # Attempt to insert document record 
            db_response = supabase.table("documents").insert(doc_record).execute()
            logger.info(f"Document record created in database")
        except Exception as db_error:
            logger.error(f"Database error: {str(db_error)}")
            # Try to clean up the uploaded file
            try:
                supabase.storage.from_("deedsure").remove([storage_path])
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up file: {str(cleanup_error)}")
            
            # If using non-admin client, provide a more specific error message
            if "violates row-level security policy" in str(db_error).lower():
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Permission denied: This operation requires admin privileges or updated RLS policies"
                )
            
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