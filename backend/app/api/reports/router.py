from fastapi import APIRouter, Depends, HTTPException, status, Body
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime
import logging

from app.core.database import get_db, get_admin_db, get_current_active_user
from app.services.report_generator import ReportGenerator

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("")
async def list_reports(
    current_user: dict = Depends(get_current_active_user)
) -> List[Dict[str, Any]]:
    """List all reports for the current user with document counts"""
    user_id = current_user.get("id")
    logging.info(f"Listing reports for user ID: {user_id}")
    
    # Get database connection
    supabase = get_db()
    
    # Fetch reports for the user
    try:
        admin_db = get_admin_db()
        if admin_db:
            logging.info("Using admin client for report listing")
            response = admin_db.table("reports").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        else:
            logging.warning("Admin database client not available, falling back to regular client")
            response = supabase.table("reports").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
        
        # Log the response
        logging.info(f"Reports count: {len(response.data) if response.data else 0}")
        
        if not response.data:
            return []
        
        reports = response.data
        
        # For each report, fetch document count
        for report in reports:
            try:
                count_response = supabase.table("report_documents").select("count", count="exact").eq("report_id", report["id"]).execute()
                document_count = count_response.count if hasattr(count_response, 'count') else 0
                report["document_count"] = document_count
            except Exception as count_error:
                logging.error(f"Error fetching document count for report {report['id']}: {str(count_error)}")
                report["document_count"] = 0
        
        return reports
    except Exception as e:
        logging.error(f"Error fetching reports: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching reports: {str(e)}"
        )
    
@router.get("/{report_id}")
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Get a specific report by ID with related documents"""
    user_id = current_user.get("id")
    logging.info(f"Fetching report ID: {report_id} for user ID: {user_id}")
    
    # Get database connection
    supabase = get_db()
    
    try:
        # Try to use admin client first
        admin_db = get_admin_db()
        if admin_db:
            logging.info("Using admin client for report fetch")
            response = admin_db.table("reports").select("*").eq("id", report_id).execute()
        else:
            logging.warning("Admin database client not available, falling back to regular client")
            response = supabase.table("reports").select("*").eq("id", report_id).execute()
        
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        report = response.data[0]
        
        # If using admin client, verify the report belongs to the current user
        if admin_db and report.get("user_id") != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this report"
            )
        
        # Fetch associated documents from the join table
        try:
            # Get document IDs from join table
            join_response = supabase.table("report_documents").select("document_id").eq("report_id", report_id).execute()
            
            document_ids = []
            if join_response.data:
                document_ids = [item["document_id"] for item in join_response.data]
            
            # If document IDs found, fetch document details
            documents = []
            if document_ids:
                for doc_id in document_ids:
                    doc_response = supabase.table("documents").select("id,filename,category,content_type,file_size").eq("id", doc_id).execute()
                    if doc_response.data and doc_response.data[0]:
                        documents.append(doc_response.data[0])
            
            # Add document info to the report
            report["documents"] = documents
            report["document_ids"] = document_ids
            
        except Exception as doc_error:
            logging.error(f"Error fetching associated documents: {str(doc_error)}")
            # Don't fail the request, just note that documents couldn't be fetched
            report["documents"] = []
            report["document_ids"] = []
            
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error fetching report: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching report: {str(e)}"
        )

@router.post("/generate")
async def generate_report(
    request_data: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """Generate a new report"""
    user_id = current_user.get("id")
    logging.info(f"Generating report for user ID: {user_id}")
    
    # Log the received request data for debugging
    logging.info(f"Received report generation request data: {request_data}")
    
    try:
        # Get selected document IDs from request
        document_ids = request_data.get("document_ids", [])
        
        if not document_ids:
            logging.error("No document IDs provided in request")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No document IDs provided for report generation"
            )
        
        # Get database connection to fetch documents
        supabase = get_db()
        
        # Fetch the selected documents
        documents = []
        for doc_id in document_ids:
            try:
                response = supabase.table("documents").select("*").eq("id", doc_id).eq("user_id", str(user_id)).execute()
                if response.data and len(response.data) > 0:
                    documents.append(response.data[0])
            except Exception as e:
                logging.error(f"Error fetching document {doc_id}: {str(e)}")
        
        if not documents:
            logging.error("No valid documents found for the provided IDs")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No valid documents found for the provided IDs"
            )
        
        # Extract text from documents
        document_texts = []
        for doc in documents:
            if doc.get("extracted_text"):
                document_texts.append(doc.get("extracted_text"))
        
        if not document_texts:
            logging.error("No extracted text found in the selected documents")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No extracted text found in the selected documents"
            )
        
        # Initialize report generator
        report_generator = ReportGenerator()
        
        # Generate the report - note we're no longer passing metadata
        try:
            logging.info(f"Generating report from {len(document_texts)} document texts")
            report_data = await report_generator.generate_report(document_texts)
            logging.info("Report generation completed successfully")
        except Exception as e:
            logging.error(f"Error in report generation: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Report generation failed: {str(e)}"
            )
        
        # Add user ID to report data
        report_data["user_id"] = str(user_id)
        
        # Get database connection for storing the report
        try:
            # Try to use admin client to bypass RLS
            admin_db = get_admin_db()
            if admin_db:
                db_client = admin_db
                logging.info("Using admin client for database operations")
            else:
                db_client = supabase
                logging.warning("Admin database client not available, falling back to regular client")
            
            # Insert the report
            db_response = db_client.table("reports").insert(report_data).execute()
            logging.info(f"Report record created in database with ID: {report_data['id']}")
        except Exception as db_error:
            logging.error(f"Database error: {str(db_error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save report: {str(db_error)}"
            )
        
        # Add document IDs to the response (but not to the database)
        response_data = report_data.copy()
        response_data["document_ids"] = document_ids
        
        return {
            "success": True,
            "report": response_data
        }
        
    except HTTPException:
        raise
    except ValueError as ve:
        logging.error(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )
    except Exception as e:
        logging.error(f"Unhandled exception: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating report: {str(e)}"
        )
