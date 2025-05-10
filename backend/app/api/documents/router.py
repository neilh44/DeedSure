from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from typing import List, Dict, Any
import uuid
from datetime import datetime
import io
from app.core.database import get_db
from app.services.document_processor import DocumentProcessor

router = APIRouter()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    # Get file content
    contents = await file.read()
    file_size = len(contents)
    
    # Generate a unique ID and filename for storage
    document_id = str(uuid.uuid4())
    storage_path = f"documents/{document_id}/{file.filename}"
    
    # Initialize document processor
    doc_processor = DocumentProcessor()
    
    # Process file content based on file type
    extracted_text = ""
    metadata = {}
    category = "unknown"
    
    if file.content_type == "application/pdf":
        # Extract text from PDF
        extracted_text = await doc_processor.extract_text_from_pdf(contents)
        
        # Categorize document
        category = await doc_processor.categorize_document(extracted_text)
        
        # Extract metadata
        metadata = await doc_processor.extract_metadata(extracted_text, category)
    
    # Get Supabase client
    supabase = get_db()
    
    # Upload to Supabase Storage
    try:
        # Convert bytes to file-like object for upload
        file_obj = io.BytesIO(contents)
        
        # Upload file to Supabase storage
        storage_response = supabase.storage.from_("documents").upload(
            path=storage_path,
            file=file_obj,
            file_options={"content_type": file.content_type}
        )
        
        # Create metadata record in database
        doc_record = {
            "id": document_id,
            "filename": file.filename,
            "storage_path": storage_path,
            "content_type": file.content_type,
            "size": file_size,
            "upload_date": datetime.now().isoformat(),
            "category": category,
            "status": "processed" if extracted_text else "uploaded",
            "extracted_text": extracted_text,
            "metadata": metadata
        }
        
        # Insert document record into database
        db_response = supabase.table("documents").insert(doc_record).execute()
        
        return {
            "id": document_id,
            "filename": file.filename,
            "content_type": file.content_type,
            "size": file_size,
            "category": category,
            "upload_date": datetime.now().isoformat(),
            "status": "processed" if extracted_text else "uploaded",
            "storage_url": supabase.storage.from_("documents").get_public_url(storage_path)
        }
        
    except Exception as e:
        # Handle exceptions and return appropriate error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading document: {str(e)}"
        )