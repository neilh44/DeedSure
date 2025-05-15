import asyncio
from typing import Dict, Any, List, Optional
import groq
import time
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with Groq LLM API with error handling"""
    
    def __init__(self):
        self.client = groq.Client(api_key=settings.GROQ_API_KEY)
        self.model = settings.LLM_MODEL
        self.token_limit_per_request = 29000
        
        logger.info(f"LLMService initialized with model {self.model}")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Roughly estimate the number of tokens in the text.
        For GPT models, ~4 chars ≈ 1 token, but this is a simple approximation.
        """
        return len(text) // 4
    
    async def analyze_documents(self, document_texts: List[str]) -> str:
        """
        Send documents to LLM for title report generation without batching
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            Structured title report text
        """
        if not document_texts:
            logger.warning("No document texts provided for analysis")
            return "Error: No documents provided for analysis."
            
        logger.info(f"Analyzing {len(document_texts)} documents with LLM without batching")
        
        try:
            # Combine all documents with a separator
            combined_text = "\n\n---DOCUMENT SEPARATOR---\n\n".join(document_texts)
            
            prompt = f"""
            Analyze the following property documents to generate a comprehensive title search report.

            ## Document Content:
            {combined_text}

            ## Instructions:
            Generate a comprehensive title search report by extracting the following information:

            1. **Basic Property Identification**
               - Survey/Block Number and UPIN
               - Village, Taluka and District location
               - Any Town Planning/Final Plot numbers
               - Boundaries or neighboring properties (if available)

            2. **Area and Assessment**
               - Total area in relevant measurement units
               - Assessment amount
               - Breakdown of area by usage (if applicable)
               - Land use classification

            3. **Current Ownership**
               - Current owner's full name/entity
               - How ownership was established (sale deed, inheritance, etc.)
               - Date of current ownership
               - Transaction details if recent

            4. **Ownership History**
               - Chain of title for at least 30 years
               - All previous owners with dates
               - Mode of transfer for each change in ownership

            5. **Land Status Changes**
               - Any conversion from agricultural to non-agricultural
               - Permissions granted with dates and order numbers
               - Premiums or fees paid for conversion
               - Development permissions

            6. **Encumbrances and Litigation**
               - All court cases related to the property
               - Status of each case and final orders
               - Any active disputes or pending litigation
               - Notices, attachments or stays

            7. **Rights and Restrictions**
               - Easements or rights of way
               - Mortgage or loan details
               - Government restrictions or conditions
               - Heritage or environmental restrictions

            8. **Revenue and Tax Status**
               - Current tax assessment
               - Payment status
               - Any arrears or dues

            9. **Additional Relevant Information**
               - Historical use of the property
               - Administrative changes affecting the property
               - Special conditions or observations

            10. **Conclusion and Recommendations**
                - Clear statement on current ownership status
                - Any red flags or issues requiring attention
                - Recommendations for further verification

            Format the report with clear headings and sections. Include all relevant details found in the documents.
            """
            
            # Estimate tokens for this request (prompt + system message)
            system_message = "You are a specialized legal assistant with expertise in property law and title searches."
            estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
            
            logger.debug(f"Estimated token usage for request: {estimated_tokens}")
            
            if estimated_tokens > self.token_limit_per_request:
                logger.warning(f"Request exceeds token limit ({estimated_tokens} > {self.token_limit_per_request}).")
                return "Error: The combined documents exceed the token limit. Please use fewer or smaller documents."
            
            # Call Groq API with retry mechanism
            max_retries = 3
            backoff_factor = 2
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"Sending request to Groq API (attempt {attempt + 1}/{max_retries})")
                    
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=8000,
                        temperature=0.2
                    )
                    
                    logger.info(f"Analysis completed")
                    return response.choices[0].message.content
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor ** attempt
                        logger.warning(f"API call failed: {str(e)}. Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"All retry attempts failed: {str(e)}")
                        raise
                    
        except Exception as e:
            logger.error(f"Error during document analysis: {str(e)}")
            return f"Error analyzing documents: {str(e)}"