from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Body
from typing import List, Dict, Any
import uuid
from datetime import datetime
import logging

from app.core.database import get_db, get_admin_db, get_current_active_user
from app.services.document_processor import DocumentProcessor
from app.services.llm_service import LLMService
from app.utils.storage import get_document_from_storage

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("")
async def list_documents(
    current_user: dict = Depends(get_current_active_user)
) -> List[Dict[str, Any]]:
    """List all documents for the current user"""
    user_id = current_user.get("id")
    logging.info(f"Listing documents for user ID: {user_id}")
    
    # Get database connection
    supabase = get_db()
    
    # Fetch documents for the user
    try:
        admin_db = get_admin_db()
        if admin_db:
            logging.info("Using admin client for document listing")
            response = admin_db.table("documents").select("*").eq("user_id", user_id).execute()
        else:
            logging.warning("Admin database client not available, falling back to regular client")
            response = supabase.table("documents").select("*").eq("user_id", user_id).execute()
        
        # Log the response
        logging.info(f"Documents response data: {response.data}")
        logging.info(f"Documents count: {len(response.data) if response.data else 0}")
        
        if response.data:
            return response.data
        return []
    except Exception as e:
        logging.error(f"Error fetching documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching documents: {str(e)}"
        )
@router.get("/{document_id}")
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Get a specific document by ID"""
    user_id = current_user.get("id")
    logging.info(f"Fetching document ID: {document_id} for user ID: {user_id}")
    
    # Get database connection
    supabase = get_db()
    
    try:
        # Try to use admin client first
        admin_db = get_admin_db()
        if admin_db:
            logging.info("Using admin client for document fetch")
            # Get document and verify it belongs to the current user
            response = admin_db.table("documents").select("*").eq("id", document_id).execute()
        else:
            logging.warning("Admin database client not available, falling back to regular client")
            # Regular client with RLS will automatically filter by user_id
            response = supabase.table("documents").select("*").eq("id", document_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {document_id} not found"
            )
        
        document = response.data[0]
        
        # If using admin client, manually verify the document belongs to the current user
        if admin_db and document.get("user_id") != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this document"
            )
        
        # Get storage URL
        storage_path = document.get("file_path")
        if storage_path:
            document["storage_url"] = supabase.storage.from_("deedsure").get_public_url(storage_path)
        
        return document
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logging.error(f"Error fetching document: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching document: {str(e)}"
        )

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
        
        # Get regular Supabase client - we'll try admin client for DB operations later
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
        
        # Handle the user_id properly - ensure it's a string UUID for JSON serialization
        try:
            # If it's already a UUID object, convert to string
            if isinstance(current_user["id"], uuid.UUID):
                current_user_id = str(current_user["id"])
            # If it's a string representation of a UUID, use it directly
            else:
                # Validate that it's a proper UUID string
                uuid.UUID(str(current_user["id"]))  # This will raise an error if invalid
                current_user_id = str(current_user["id"])
            
            logger.info(f"Using user ID: {current_user_id} (type: {type(current_user_id).__name__})")
        except Exception as uid_error:
            logger.error(f"Error handling user ID: {str(uid_error)}")
            # Fall back to using it as-is but still as a string
            current_user_id = str(current_user["id"])
            logger.info(f"Falling back to string user ID: {current_user_id}")
        
        # Now create the document record in the database - try admin client first
        try:
            # Try to get admin client to bypass RLS
            try:
                db_client = get_admin_db()
                logger.info("Using admin client for database operations")
            except Exception:
                logger.warning("Could not get admin client, falling back to regular client")
                db_client = get_db()
            
            # Prepare document record with fields that match the database schema
            doc_record = {
                "id": document_id,
                "user_id": current_user_id,  # Now a string UUID, which is JSON serializable
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
            logger.info(f"user_id type: {type(doc_record['user_id']).__name__}")
            
            # Attempt to insert document record 
            db_response = db_client.table("documents").insert(doc_record).execute()
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
    
@router.post("/{document_id}/process")
async def process_document(
    document_id: str
) -> Dict[str, Any]:
    """Process an already uploaded document to extract text and metadata"""
    # Get database connection
    supabase = get_db()
    
    try:
        # Retrieve document from Supabase
        file_content, document = await get_document_from_storage(supabase, document_id)
        
        # Update document status to processing
        supabase.table("documents").update({
            "status": "processing"
        }).eq("id", document_id).execute()
        
        # Extract text based on content type
        content_type = document.get("content_type", "")
        if "pdf" in content_type.lower():
            extracted_text = await DocumentProcessor.extract_text_from_pdf(file_content)
        else:
            # Handle other file types or raise an error
            raise ValueError(f"Unsupported content type: {content_type}")
        
        # Categorize the document
        category = await DocumentProcessor.categorize_document(extracted_text)
        
        # Extract metadata
        metadata = await DocumentProcessor.extract_metadata(extracted_text, category)
        
        # Update the document record with processed information
        supabase.table("documents").update({
            "status": "processed",
            "category": category,
            "extracted_text": extracted_text,
            "metadata": metadata,
            "processed_at": datetime.now().isoformat()
        }).eq("id", document_id).execute()
        
        return {
            "id": document_id,
            "status": "processed",
            "category": category,
            "metadata": metadata,
            "message": "Document processed successfully"
        }
        
    except Exception as e:
        # Update status to failed if an error occurs
        try:
            supabase.table("documents").update({
                "status": "failed", 
                "error": str(e)
            }).eq("id", document_id).execute()
        except:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document processing failed: {str(e)}"
        )


@router.post("/{document_id}/analyze")
async def analyze_document(
    document_id: str
) -> Dict[str, Any]:
    """Analyze a document using the LLM service"""
    # Get database connection
    supabase = get_db()
    
    try:
        # Check if document exists and has been processed
        response = supabase.table("documents").select("*").eq("id", document_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {document_id} not found"
            )
        
        document = response.data[0]
        
        # Check if document has extracted text
        if not document.get("extracted_text"):
            # If not processed, process it first
            if document.get("status") != "processed":
                await process_document(document_id)
                # Get updated document
                response = supabase.table("documents").select("*").eq("id", document_id).execute()
                document = response.data[0]
        
        # Get extracted text
        extracted_text = document.get("extracted_text", "")
        
        if not extracted_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document has no extracted text to analyze"
            )
        
        # Create LLM service
        llm_service = LLMService()
        
        # Send to LLM for analysis
        analysis_result = await llm_service.analyze_single_document(extracted_text)
        
        # Store analysis in the database
        analysis_id = str(uuid.uuid4())
        analysis_record = {
            "id": analysis_id,
            "document_id": document_id,
            "analysis_type": "single_document",
            "analysis_date": datetime.now().isoformat(),
            "content": analysis_result
        }
        
        # Insert analysis record
        supabase.table("document_analyses").insert(analysis_record).execute()
        
        return {
            **analysis_record,
            "message": "Document analyzed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Document analysis failed: {str(e)}"
        )


@router.get("/{document_id}/analyses")
async def list_document_analyses(document_id: str) -> List[Dict[str, Any]]:
    """List all analyses for a document"""
    # Get database connection
    supabase = get_db()
    
    # Check if document exists
    doc_response = supabase.table("documents").select("id").eq("id", document_id).execute()
    
    if not doc_response.data or len(doc_response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found"
        )
    
    # Get analyses for the document
    response = supabase.table("document_analyses").select("*").eq("document_id", document_id).order("analysis_date", desc=True).execute()
    
    if response.data:
        return response.data
    return []


@router.get("/analyses/{analysis_id}")
async def get_document_analysis(analysis_id: str) -> Dict[str, Any]:
    """Get a specific document analysis"""
    # Get database connection
    supabase = get_db()
    
    # Get analysis by ID
    response = supabase.table("document_analyses").select("*").eq("id", analysis_id).execute()
    
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis with ID {analysis_id} not found"
        )
    
    return response.data[0]
