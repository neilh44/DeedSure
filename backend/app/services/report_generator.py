from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import logging
from .llm_service import LLMService
from .document_processor import DocumentProcessor

# Set up logging
logger = logging.getLogger(__name__)

class ReportGenerator:
    """Service for generating title search reports"""
    
    def __init__(self):
        self.llm_service = LLMService()
        
    async def generate_report(self, 
                              document_texts: List[str], 
                              metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a title search report from document texts
        
        Args:
            document_texts: List of extracted document texts
            metadata: Optional additional metadata to include
            
        Returns:
            Dict containing report data
        """
        # Validate inputs with better error handling
        if not document_texts:
            logger.error("Empty document_texts provided")
            raise ValueError("Document texts must be a non-empty list of strings")
            
        if not isinstance(document_texts, list):
            # Try to convert to list if it's not one
            try:
                logger.warning(f"Converting document_texts from {type(document_texts)} to list")
                document_texts = list(document_texts)
            except:
                logger.error(f"Could not convert document_texts of type {type(document_texts)} to list")
                raise ValueError("Document texts must be a non-empty list of strings")
        
        # Convert any non-string elements to strings
        processed_texts = []
        for text in document_texts:
            if not text:
                continue
            if not isinstance(text, str):
                logger.warning(f"Converting non-string document text of type {type(text)} to string")
                text = str(text)
            processed_texts.append(text)
        
        if not processed_texts:
            logger.error("No valid document texts found after processing")
            raise ValueError("No valid document texts found after processing")
            
        # Process with LLM - add error handling
        try:
            logger.info(f"Sending {len(processed_texts)} texts to LLM for analysis")
            report_content = await self.llm_service.analyze_documents(processed_texts)
            logger.info("LLM analysis completed successfully")
        except Exception as e:
            # Log the error and re-raise
            logger.error(f"LLM analysis failed: {str(e)}")
            raise ValueError(f"Failed to analyze documents: {str(e)}")
        
        # Create report object with properly formatted data
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id,
            "created_at": datetime.now().isoformat(),
            "content": report_content,
            "status": "completed",
            "source_document_count": len(processed_texts)
        }
        
        # Extract title if possible, with better handling
        title_line = None
        if report_content:
            content_lines = report_content.split("\n")
            for line in content_lines[:10]:  # Only check first 10 lines
                if line and (line.strip().startswith("Re:") or line.strip().startswith("Re.:")): 
                    title_line = line.replace("Re:", "").replace("Re.:", "").strip()
                    break
        
        if title_line:
            report["title"] = f"Title Report - {title_line[:50]}"
        else:
            report["title"] = f"Title Report - {datetime.now().strftime('%Y-%m-%d')}"
        
        # Add any additional metadata with validation
        if metadata and isinstance(metadata, dict):
            # Ensure metadata doesn't contain any invalid types for JSON
            sanitized_metadata = {}
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                    sanitized_metadata[key] = value
            report["metadata"] = sanitized_metadata
            
        logger.info(f"Generated report with ID: {report_id}")
        return report
        
    # Add a method to handle API endpoint compatibility
    async def generate_report_for_api(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Adapter method to handle API request data format
        
        Args:
            request_data: The request data from the API
            
        Returns:
            Properly formatted report
        """
        # Extract necessary fields from request data
        logger.info(f"Processing API request data: {request_data.keys() if request_data else 'None'}")
        
        # Basic validation
        if not request_data:
            logger.error("Empty request data")
            raise ValueError("Request data is empty")
            
        # Extract document texts - handle different possible formats
        document_texts = []
        if "documents" in request_data:
            # Standard format
            document_texts = request_data.get("documents", [])
            logger.info(f"Found {len(document_texts)} documents in standard format")
        elif "document_ids" in request_data:
            # Format with document IDs - would need to fetch documents
            logger.error("Request format with document_ids is not supported yet")
            raise ValueError("Request format with document_ids is not supported yet")
        elif "document_texts" in request_data:
            # Alternative format
            document_texts = request_data.get("document_texts", [])
            logger.info(f"Found {len(document_texts)} documents in alternative format")
        
        # Extract metadata
        metadata = request_data.get("metadata", {})
        
        # Validate required fields
        if not document_texts:
            logger.error("No documents provided in request")
            raise ValueError("No documents provided in request")
            
        # Call main report generation method
        try:
            report = await self.generate_report(document_texts, metadata)
            logger.info("Report generated successfully")
            # Format for API response
            return {
                "success": True,
                "report": report
            }
        except Exception as e:
            logger.error(f"Failed to generate report: {str(e)}")
            raise ValueError(f"Failed to generate report: {str(e)}")