import asyncio
from typing import Dict, Any, List, Optional
import groq
import time
import logging
from collections import deque
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with Groq LLM API with rate limiting and error handling"""
    
    def __init__(self):
        self.client = groq.Client(api_key=settings.GROQ_API_KEY)
        self.model = settings.LLM_MODEL
        
        # Rate limiting settings
        self.token_limit_per_minute = 6000
        self.token_limit_per_request = 6000
        self.token_history = deque()  # Stores (timestamp, token_count) tuples
        self.window_size_seconds = 60  # 1 minute window
        
        logger.info(f"LLMService initialized with model {self.model}, token limit {self.token_limit_per_minute}/minute, and {self.token_limit_per_request}/request")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Roughly estimate the number of tokens in the text.
        For GPT models, ~4 chars ≈ 1 token, but this is a simple approximation.
        """
        return len(text) // 4
    
    def _update_token_history(self, tokens_used: int) -> None:
        """
        Add tokens to history and remove entries older than window size
        """
        current_time = time.time()
        self.token_history.append((current_time, tokens_used))
        
        # Remove entries older than our window
        while self.token_history and self.token_history[0][0] < current_time - self.window_size_seconds:
            self.token_history.popleft()
        
        current_usage = self._get_current_token_usage()
        logger.debug(f"Token usage updated: {current_usage}/{self.token_limit_per_minute} in current window")
    
    def _get_current_token_usage(self) -> int:
        """
        Calculate total tokens used in the current time window
        """
        return sum(tokens for _, tokens in self.token_history)
    
    def _check_rate_limit(self, estimated_tokens: int) -> float:
        """
        Check if sending this many tokens would exceed rate limit
        Returns wait time in seconds, or 0 if no wait needed
        """
        current_usage = self._get_current_token_usage()
        
        if current_usage + estimated_tokens <= self.token_limit_per_minute:
            return 0
        
        # Calculate how long to wait
        if not self.token_history:
            return 0
            
        oldest_timestamp = self.token_history[0][0]
        time_to_wait = (oldest_timestamp + self.window_size_seconds) - time.time()
        wait_time = max(0, time_to_wait)
        
        if wait_time > 0:
            logger.info(f"Rate limit would be exceeded. Waiting {wait_time:.2f}s before processing. " 
                      f"Current usage: {current_usage}/{self.token_limit_per_minute}")
        
        return wait_time
    
    async def analyze_documents(self, document_texts: List[str]) -> str:
        """
        Process documents sequentially, one at a time
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            Structured title report text
        """
        if not document_texts:
            logger.warning("No document texts provided for analysis")
            return "Error: No documents provided for analysis."
            
        logger.info(f"Sequentially analyzing {len(document_texts)} documents with LLM")
        
        # Process one document at a time
        accumulated_report = ""
        system_message = "You are an expert legal title examiner with decades of experience in property law, land records, and title searches. You meticulously extract EVERY detail from land records to create exhaustive title reports that document the complete chain of title without omitting any information. Your specialty is creating detailed chronological ownership histories that capture every entry in land records without summarization."
        
        for i, doc_text in enumerate(document_texts):
            try:
                logger.info(f"Processing document {i+1}/{len(document_texts)}")
                
                prompt = ""
                # For the first document, create a new report
                if i == 0:
                    prompt = f"""
                    Analyze the following property document to generate an extremely detailed and comprehensive title search report. Pay particular attention to extracting EVERY entry in the chronological chain of title.

                    ## Document Content:
                    {doc_text}

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
                # For subsequent documents, update the existing report
                else:
                    prompt = f"""
                    You are continuing a title search report analysis. Review the additional property document below and update or expand your previous analysis.

                    ## Previous Analysis:
                    {accumulated_report}

                    ## New Document Content:
                    {doc_text}

                    ## Instructions:
                    Carefully analyze this new document and update your previous title report. When updating:
                    
                    1. Integrate all new information with your previous analysis
                    2. Maintain chronological order in the chain of title
                    3. Add any new information about property identification, ownership, encumbrances, etc.
                    4. Update sections as needed based on new information
                    5. If there are conflicts between documents, note them explicitly
                    6. Preserve the comprehensive structure of the report
                    7. Ensure no details from the previous analysis or new document are omitted
                    8. Update conclusions and recommendations based on the complete set of documents

                    FORMAT REQUIREMENTS:
                    - Maintain the same comprehensive structure as the previous report
                    - Ensure ALL information is directly extracted from the documents
                    - Bold all key facts, dates, and figures
                    - Present complete information without summarizing
                    - If information appears to be missing or unclear, explicitly note this

                    Produce an updated, comprehensive report that incorporates ALL information from BOTH the previous analysis and this new document.
                    """
                
                # Estimate tokens for this request
                estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
                
                logger.debug(f"Estimated token usage for request {i+1}: {estimated_tokens}")
                
                if estimated_tokens > self.token_limit_per_request:
                    logger.warning(f"Request exceeds token limit ({estimated_tokens} > {self.token_limit_per_request}).")
                    return f"Error: Document {i+1} processing would exceed the token limit. Please split the document or modify the approach."
                
                # Check rate limit
                wait_time = self._check_rate_limit(estimated_tokens)
                if wait_time > 0:
                    logger.info(f"Rate limit would be exceeded. Waiting {wait_time:.2f}s before processing document {i+1}.")
                    await asyncio.sleep(wait_time)
                # If at token limit, wait a full minute to clear the window
                elif self._get_current_token_usage() >= self.token_limit_per_minute * 0.9:  # 90% threshold
                    logger.info(f"Approaching rate limit. Pausing for 60 seconds before processing document {i+1}.")
                    await asyncio.sleep(60)
                
                # Call Groq API with retry mechanism
                max_retries = 3
                backoff_factor = 2
                
                for attempt in range(max_retries):
                    try:
                        logger.info(f"Sending document {i+1} to Groq API (attempt {attempt + 1}/{max_retries})")
                        
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=[
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": prompt}
                            ],
                            max_tokens=8000,
                            temperature=0.0  # Zero temperature for maximum factual accuracy
                        )
                        
                        # Update token usage tracking
                        tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                        self._update_token_history(tokens_used)
                        
                        # Update accumulated report with this response
                        accumulated_report = response.choices[0].message.content
                        
                        logger.info(f"Document {i+1}/{len(document_texts)} processed successfully. Tokens used: {tokens_used}")
                        break
                        
                    except Exception as e:
                        if attempt < max_retries - 1:
                            wait_time = backoff_factor ** attempt
                            logger.warning(f"API call failed: {str(e)}. Retrying in {wait_time}s...")
                            await asyncio.sleep(wait_time)
                        else:
                            logger.error(f"All retry attempts failed for document {i+1}: {str(e)}")
                            raise
            
            except Exception as e:
                logger.error(f"Error processing document {i+1}: {str(e)}")
                return f"Error analyzing document {i+1}: {str(e)}"
        
        logger.info(f"Sequential analysis of {len(document_texts)} documents completed successfully")
        return accumulated_report