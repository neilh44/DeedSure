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
            Analyze the following property documents to generate an extremely detailed and comprehensive title search report. Pay particular attention to extracting EVERY entry in the chronological chain of title.

            ## Document Content:
            {combined_text}

            ## Instructions:
            You must carefully examine all pages of the land record document and extract EVERY detail to produce a comprehensive title search report with the following sections:

            1. **Basic Property Identification**
               - Survey/Block Number and UPIN
               - Village, Taluka and District location
               - Any Town Planning/Final Plot numbers
               - Boundaries or neighboring properties (if available)
               - Detailed property description including location indicators

            2. **Area and Assessment**
               - Total area in relevant measurement units (specify hectares, acres, square meters, etc.)
               - Assessment amount with currency
               - Breakdown of area by usage (residential, commercial, etc.)
               - Land use classification (agricultural, non-agricultural, etc.)
               - Any other area-related details mentioned in the record

            3. **Current Ownership**
               - Current owner's full name/entity with EXACT spelling from the record
               - How ownership was established (specific sale deed number, inheritance, etc.)
               - Exact date of current ownership acquisition
               - Transaction details including consideration amount, registration details
               - Percentage/share of ownership if multiple owners

            4. **EXHAUSTIVE Chronological Chain of Title**
               - Extract EVERY SINGLE entry from the "Entry Details" section of the record
               - Format as a detailed table with these columns:
                  * Entry/Note Number
                  * Entry Date
                  * Transaction Type
                  * Transferor(s) (seller/previous owner)
                  * Transferee(s) (buyer/new owner)
                  * Transaction Details
                  * Consideration Amount (if sale)
                  * Special Conditions or Notes
               - Present entries in strict chronological order from earliest to most recent
               - Include ALL entries visible in the document without omitting ANY details
               - For each entry, explain its significance to the chain of title
               - Do not summarize or abbreviate entries - include complete information
               - Ensure proper tracking of ownership shares/percentages when multiple owners
               - Cross-reference entry numbers mentioned in different sections of the document

            5. **Land Status Changes**
               - Detail ALL changes from agricultural to non-agricultural use
               - Include all permissions with dates, authority granting permission, and order numbers
               - List all premiums or fees paid for conversion with exact amounts
               - Document all development permissions with relevant details
               - Note any conditions attached to conversions or permissions

            6. **Comprehensive Encumbrances and Litigation History**
               - Extract ALL court cases from the document with their numbers and dates
               - Document the complete history of each case including:
                  * Parties involved
                  * Nature of dispute
                  * Filing dates
                  * Court/authority hearing the case
                  * Case status (pending, disposed, etc.)
                  * Final orders with dates and implications
               - Include ALL entries from the "Boja and Other Rights Details" section
               - Document ALL notices, attachments, or stays affecting the property
               - Note ALL mortgage details if mentioned

            7. **Rights and Restrictions**
               - Document ALL easements or rights of way
               - Extract ALL mortgage or loan details
               - List ALL government restrictions or conditions
               - Note ANY other restrictions on property usage

            8. **Revenue and Tax Status**
               - Current tax assessment with exact amount
               - Payment status if mentioned
               - Any arrears or dues
               - Historical tax assessment changes if available

            9. **Crop and Land Use History**
               - Extract information from the "Crop Details" section
               - Document historical crop patterns and land usage
               - Note irrigation details if mentioned

            10. **Additional Relevant Information**
                - Document ALL administrative changes affecting the property
                - Note ALL special conditions or observations
                - Include ANY other relevant information from the document

            11. **Conclusion and Recommendations**
                - Provide a clear statement on current ownership status
                - List ALL potential red flags or issues requiring attention
                - Offer specific recommendations for further verification
                - Comment on the completeness of the title based on the document

            FORMAT REQUIREMENTS:
            - Begin with a clear title and date of report
            - Use numbered sections with clear headings
            - Present the chain of title as a detailed chronological table
            - For entries with extensive details, provide complete information rather than summarizing
            - Bold key facts, dates, and figures
            - Ensure ALL information is directly extracted from the document
            - DO NOT invent or assume details not present in the document
            - If information appears to be missing or unclear, explicitly note this

            Your report MUST be EXHAUSTIVE - do not omit ANY details from the document. This report will be used for legal purposes, so accuracy and completeness are absolutely critical.
            """
            
            # Estimate tokens for this request (prompt + system message)
            system_message = "You are an expert legal title examiner with decades of experience in property law, land records, and title searches. You meticulously extract EVERY detail from land records to create exhaustive title reports that document the complete chain of title without omitting any information. Your specialty is creating detailed chronological ownership histories that capture every entry in land records without summarization."
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
                        temperature=0.0  # Zero temperature for maximum factual accuracy
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