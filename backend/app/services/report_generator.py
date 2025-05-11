from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import logging
from .llm_service import LLMService

# Set up logging
logger = logging.getLogger(__name__)

class ReportGenerator:
    """Service for generating title search reports"""
    
    def __init__(self):
        self.llm_service = LLMService()
        
    async def generate_report(self, 
                              document_texts: List[str]) -> Dict[str, Any]:
        """
        Generate a title search report from document texts
        
        Args:
            document_texts: List of extracted document texts
            
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
        
        # Create report object with only the fields we know exist in the database
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id,
            "created_at": datetime.now().isoformat(),
            "content": report_content,
            "status": "completed"
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
            
        logger.info(f"Generated report with ID: {report_id}")
        return report