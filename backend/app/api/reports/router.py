# File: /Users/nileshhanotia/Projects/Title_search/legal-title-search/backend/app/api/reports/router.py

from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime
from app.core.database import get_db
from app.services.report_generator import ReportGenerator

router = APIRouter()

@router.post("/generate")
async def generate_report(
    document_ids: List[str] = Body(...),
) -> Dict[str, Any]:
    # Initialize Supabase client
    supabase = get_db()
    
    # Check if all documents exist
    document_texts = []
    document_records = []
    
    for doc_id in document_ids:
        # Fetch document from Supabase
        response = supabase.table("documents").select("*").eq("id", doc_id).execute()
        
        # Check if document exists
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document with ID {doc_id} not found"
            )
        
        document = response.data[0]
        document_records.append(document)
        
        # Add document text to list for processing
        if document.get("extracted_text"):
            document_texts.append(document["extracted_text"])
        else:
            # If no extracted text, add a note
            document_texts.append(f"[No text extracted from document: {document['filename']}]")
    
    # Generate report ID
    report_id = str(uuid.uuid4())
    
    # Create initial report record
    report_record = {
        "id": report_id,
        "title": f"Title Report - {datetime.now().strftime('%Y-%m-%d')}",
        "status": "processing",
        "document_ids": document_ids,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
    
    # Insert initial report record
    supabase.table("reports").insert(report_record).execute()
    
    # Initialize report generator
    report_generator = ReportGenerator()
    
    try:
        # Generate the report
        metadata = {"document_count": len(document_ids)}
        report_data = await report_generator.generate_report(document_texts, metadata)
        
        # Update report record with generated content
        update_data = {
            "title": report_data["title"],
            "status": "completed",
            "content": report_data["content"],
            "metadata": report_data.get("metadata", {}),
            "updated_at": datetime.now().isoformat()
        }
        
        supabase.table("reports").update(update_data).eq("id", report_id).execute()
        
        # Return the report data
        return {
            "id": report_id,
            "title": report_data["title"],
            "status": "completed",
            "document_ids": document_ids,
            "created_at": report_record["created_at"],
            "message": "Report generated successfully"
        }
        
    except Exception as e:
        # Update report status to error
        supabase.table("reports").update({
            "status": "error",
            "error_message": str(e),
            "updated_at": datetime.now().isoformat()
        }).eq("id", report_id).execute()
        
        # Raise exception
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating report: {str(e)}"
        )

@router.get("/")
async def list_reports() -> List[Dict[str, Any]]:
    # Initialize Supabase client
    supabase = get_db()
    
    # Fetch reports from Supabase
    response = supabase.table("reports").select("id,title,created_at,status").order("created_at", desc=True).execute()
    
    # Return reports data
    return response.data

@router.get("/{report_id}")
async def get_report(report_id: str) -> Dict[str, Any]:
    # Initialize Supabase client
    supabase = get_db()
    
    # Fetch report from Supabase
    response = supabase.table("reports").select("*").eq("id", report_id).execute()
    
    # Check if report exists
    if not response.data or len(response.data) == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found"
        )
    
    report = response.data[0]
    
    # Get document details for reference
    if report.get("document_ids"):
        documents = []
        for doc_id in report["document_ids"]:
            doc_response = supabase.table("documents").select("id,filename,category").eq("id", doc_id).execute()
            if doc_response.data and len(doc_response.data) > 0:
                documents.append(doc_response.data[0])
        
        report["documents"] = documents
    
    return report