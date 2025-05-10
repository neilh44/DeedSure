# backend/app/utils/storage.py
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple

async def get_document_from_storage(supabase, document_id: str) -> Tuple[bytes, Dict[str, Any]]:
    """
    Retrieve document content and metadata from Supabase
    
    Args:
        supabase: Supabase client
        document_id: Document ID
        
    Returns:
        Tuple containing (file_content_bytes, document_metadata)
    """
    # Get document metadata from database
    response = supabase.table("documents").select("*").eq("id", document_id).execute()
    
    if not response.data or len(response.data) == 0:
        raise ValueError(f"Document with ID {document_id} not found")
    
    document = response.data[0]
    
    # Get file content from storage
    bucket_name = "documents"
    storage_path = document.get("storage_path")
    
    if not storage_path:
        raise ValueError(f"Document {document_id} has no storage path")
    
    # Download file content
    file_bytes = supabase.storage.from_(bucket_name).download(storage_path)
    
    return file_bytes, document