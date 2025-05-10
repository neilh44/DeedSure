from typing import Dict, Any, List, Optional
import groq
from app.core.config import settings

class LLMService:
    """Service for interacting with Groq LLM API"""
    
    def __init__(self):
        self.client = groq.Client(api_key=settings.GROQ_API_KEY)
        self.model = settings.LLM_MODEL
    
    async def analyze_documents(self, document_texts: List[str]) -> str:
        """
        Send documents to LLM for title report generation
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            Structured title report text
        """
        combined_text = "\n\n---DOCUMENT SEPARATOR---\n\n".join(document_texts)
        
        prompt = f"""
        You are a specialized legal assistant with expertise in property law and title searches. 
        Analyze the following property documents to generate a comprehensive title report.

        ## Instructions:
        1. Extract all relevant property details (IDs, measurements, locations)
        2. Identify all parties in the chain of title chronologically
        3. Note all transfers, deeds, and official registrations with dates
        4. Document any encumbrances, restrictions or claims
        5. Flag any potential title issues or missing information
        6. Format the report according to the standardized template below

        ## Document Content:
        {combined_text}

        ## Title Report Format:

        # REPORT ON TITLE
        Date: [Current Date]

        Re.: [Include detailed property description with Survey/Block numbers, measurements, location details, and current owner information]

        That we have caused necessary searches to be taken with the available Revenue records and Sub-Registry Records for a period of last more than Thirty Years and on perusal and verification of documents of title deeds produced to us, we give our report on title in respect of said land as under:

        1. [Original ownership details]

        2. [Chronological chain of title with numbered points]
           - Include all transfers with dates
           - Registration details (serial numbers, dates)
           - Mutation entry details
           - Inheritance information where applicable
           - Conversion details (if applicable)
           - Town Planning Scheme allocations (if applicable)

        [Continue numbered sequence for complete chain of title]

        [Public notice details if applicable]

        [Declaration details if applicable]

        THE SCHEDULE ABOVE REFERRED TO

        ALL THAT piece and parcel of [land classification] bearing [survey/plot numbers] admeasuring [measurements] of [location details] and the same is bounded as follows:

        On or towards the East  : [boundary]
        On or towards the West  : [boundary]
        On or towards the North : [boundary]
        On or towards the South : [boundary]

        [Note any limitations or special considerations]

        [Signature Block]
        """
        
        # Call Groq API
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a specialized legal assistant with expertise in property law and title searches."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=8000,
            temperature=0.2
        )
        
        return response.choices[0].message.content
