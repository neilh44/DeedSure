from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
from .llm_service import LLMService
from .document_processor import DocumentProcessor

class ReportGenerator:
    """Service for generating title search reports"""
    
    def __init__(self):
        self.llm_service = LLMService()
    
    async def generate_report(self, document_texts: List[str], metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Generate a title search report from document texts
        
        Args:
            document_texts: List of extracted document texts
            metadata: Optional additional metadata to include
            
        Returns:
            Dict containing report data
        """
        # Process with LLM
        report_content = await self.llm_service.analyze_documents(document_texts)
        
        # Create report object
        report = {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now().isoformat(),
            "content": report_content,
            "status": "completed"
        }
        
        # Extract title if possible
        title_line = None
        content_lines = report_content.split("\n")
        for line in content_lines:
            if line.startswith("Re.:"):
                title_line = line.replace("Re.:", "").strip()
                break
        
        if title_line:
            report["title"] = f"Title Report - {title_line[:50]}"
        else:
            report["title"] = f"Title Report - {datetime.now().strftime('%Y-%m-%d')}"
        
        # Add any additional metadata
        if metadata:
            report["metadata"] = metadata
            
        return report
