from typing import Dict, Any, List, Optional
import PyPDF2
from io import BytesIO
import os

class DocumentProcessor:
    """Service for processing uploaded documents"""
    
    @staticmethod
    async def extract_text_from_pdf(file_content: bytes) -> str:
        """Extract text content from a PDF file"""
        pdf_file = BytesIO(file_content)
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            text += page.extract_text()
            
        return text
    
    @staticmethod
    async def categorize_document(text: str) -> str:
        """
        Categorize document based on its content
        Returns: category (deed, survey, registry, etc.)
        """
        # Simple keyword-based categorization - would be more sophisticated in production
        keywords = {
            "deed": ["deed", "transfer", "conveyance"],
            "survey": ["survey", "plot", "measurement"],
            "registry": ["registry", "registered", "register"],
        }
        
        text_lower = text.lower()
        for category, words in keywords.items():
            for word in words:
                if word in text_lower:
                    return category
                    
        return "other"
    
    @staticmethod
    async def extract_metadata(text: str, category: str) -> Dict[str, Any]:
        """
        Extract metadata from document text based on category
        Returns: Dictionary of metadata fields
        """
        # Placeholder implementation - would use more sophisticated NLP in production
        metadata = {
            "category": category,
            "processed_at": "2025-05-10T00:00:00",
            "extracted_fields": {}
        }
        
        # Very simple example extraction - would be much more robust in production
        if "property" in text.lower():
            # Find paragraph with "property" and take next 200 chars
            property_idx = text.lower().find("property")
            if property_idx >= 0:
                metadata["extracted_fields"]["property_description"] = text[property_idx:property_idx+200]
        
        return metadata
