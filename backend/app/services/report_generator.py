from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
from .llm_service import LLMService
from .document_processor import DocumentProcessor

class ReportGenerator:
    """Service for generating title search reports"""
    
    def __init__(self):
        self.llm_service = LLMService()
        self.document_processor = DocumentProcessor()
    
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
        # Validate inputs
        if not document_texts or not isinstance(document_texts, list):
            raise ValueError("Document texts must be a non-empty list of strings")
            
        # Process documents first (assuming DocumentProcessor has a process method)
        processed_texts = [
            self.document_processor.process(text) for text in document_texts
        ]
        
        # Process with LLM - add error handling
        try:
            report_content = await self.llm_service.analyze_documents(processed_texts)
        except Exception as e:
            # Log the error and re-raise with more context
            print(f"LLM analysis failed: {str(e)}")
            raise RuntimeError(f"Failed to analyze documents: {str(e)}")
        
        # Create report object with properly formatted data
        report = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat(),
            "content": report_content,
            "status": "completed",
            "source_document_count": len(document_texts)
        }
        
        # Extract title if possible, with better handling
        title_line = None
        content_lines = report_content.split("\n")
        for line in content_lines[:10]:  # Only check first 10 lines
            if line.strip().startswith("Re:") or line.strip().startswith("Re.:"): 
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
        document_texts = request_data.get("documents", [])
        metadata = request_data.get("metadata", {})
        
        # Validate required fields
        if not document_texts:
            raise ValueError("No documents provided in request")
            
        # Call main report generation method
        report = await self.generate_report(document_texts, metadata)
        
        # Format for API response
        return {
            "success": True,
            "report": report
        }