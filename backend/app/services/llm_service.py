import asyncio
from typing import Dict, Any, List, Optional
import groq
import time
import logging
import uuid
from collections import deque
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with Groq LLM API with rate limiting and error handling"""
    
    def __init__(self):
        self.client = groq.Client(api_key=settings.GROQ_API_KEY)
        self.model = settings.LLM_MODEL
        
        # Rate limiting settings - based on actual Groq limits
        self.requests_per_minute = 10
        self.tokens_per_minute = 100000
        self.token_limit_per_request = 8000  # Conservative estimate for context window
        
        # Track request history for rate limiting
        self.request_history = deque()  # Stores timestamps of requests
        self.window_size_seconds = 60  # 1 minute window
        
        logger.info(f"LLMService initialized with model {self.model}, "
                   f"limits: {self.requests_per_minute} requests/minute, "
                   f"{self.tokens_per_minute} tokens/minute")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Roughly estimate the number of tokens in the text.
        For GPT models, ~4 chars ≈ 1 token, but this is a simple approximation.
        """
        return len(text) // 4
    
    def _update_request_history(self) -> None:
        """
        Add current timestamp to request history and remove entries older than window size
        """
        current_time = time.time()
        self.request_history.append(current_time)
        
        # Remove entries older than our window
        while self.request_history and self.request_history[0] < current_time - self.window_size_seconds:
            self.request_history.popleft()
        
        logger.debug(f"Request history updated: {len(self.request_history)}/{self.requests_per_minute} in current window")
    
    def _check_rate_limit(self) -> float:
        """
        Check if we would exceed rate limit with a new request
        Returns wait time in seconds, or 0 if no wait needed
        """
        # Clean up old entries first
        current_time = time.time()
        while self.request_history and self.request_history[0] < current_time - self.window_size_seconds:
            self.request_history.popleft()
            
        # Check if we've hit the request limit
        if len(self.request_history) >= self.requests_per_minute:
            # Calculate how long to wait
            oldest_timestamp = self.request_history[0]
            time_to_wait = (oldest_timestamp + self.window_size_seconds) - current_time
            wait_time = max(0, time_to_wait + 0.1)  # Add a small buffer
            
            if wait_time > 0:
                logger.info(f"Rate limit would be exceeded. Waiting {wait_time:.2f}s before processing. " 
                          f"Current usage: {len(self.request_history)}/{self.requests_per_minute} requests")
            
            return wait_time
            
        return 0
    
    async def process_single_document(self, doc_text: str, doc_index: int) -> str:
        """
        Process a single document and generate a report
        
        Args:
            doc_text: Text content of the document
            doc_index: Index of the document (for logging)
            
        Returns:
            Title report for this document
        """
        # Check if document is too large
        estimated_tokens = self._estimate_tokens(doc_text)
        if estimated_tokens > self.token_limit_per_request * 0.6:  # Leave room for prompt and completion
            logger.warning(f"Document {doc_index} too large ({estimated_tokens} est. tokens)")
            return f"ERROR: Document {doc_index} exceeds token limits with approximately {estimated_tokens} tokens."
        
        # Check rate limit
        wait_time = self._check_rate_limit()
        if wait_time > 0:
            logger.info(f"Waiting {wait_time:.2f}s before processing document {doc_index} due to rate limits")
            await asyncio.sleep(wait_time)
        
        # Using your detailed prompt for individual document processing
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
        
        system_message = "You are an expert legal title examiner with decades of experience in property law, land records, and title searches. You meticulously extract EVERY detail from land records to create exhaustive title reports that document the complete chain of title without omitting any information. Your specialty is creating detailed chronological ownership histories that capture every entry in land records without summarization."
        
        # Call Groq API with retry mechanism
        max_retries = 3
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending document {doc_index} to Groq API (attempt {attempt + 1}/{max_retries})")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=8000,
                    temperature=0.0   # Zero temperature for factual accuracy
                )
                
                # Update rate limiting history
                self._update_request_history()
                
                logger.info(f"Document {doc_index} processed successfully. Tokens: {response.usage.total_tokens}")
                return response.choices[0].message.content
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"API call failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed: {str(e)}")
                    raise
    
    async def combine_reports(self, reports: List[str]) -> str:
        """
        Combine multiple individual reports into a single comprehensive report
        
        Args:
            reports: List of individual document reports
            
        Returns:
            Combined title report
        """
        if not reports:
            return "No reports to combine."
        
        if len(reports) == 1:
            return reports[0]
        
        # Check rate limit before combining
        wait_time = self._check_rate_limit()
        if wait_time > 0:
            logger.info(f"Waiting {wait_time:.2f}s before combining reports due to rate limits")
            await asyncio.sleep(wait_time)
        
        # Prepare individual reports for combining
        report_sections = []
        for i, report in enumerate(reports):
            # Process each report to extract the most important information
            # Limit size to avoid token limits
            max_chars = 3000  # Approximately 750 tokens per report
            summary = report[:max_chars]
            if len(report) > max_chars:
                summary += "... [truncated for combination]"
            report_sections.append(f"--- REPORT {i+1} ---\n{summary}\n")
        
        combined_reports = "\n\n".join(report_sections)
        
        # Using your detailed prompt format for report combination
        prompt = f"""
        You are continuing a title search report analysis. You have analyzed multiple property documents and generated individual reports.
        Now combine these reports into a single comprehensive title report.

        ## Previous Reports:
        {combined_reports}

        ## Instructions:
        Carefully analyze these reports and create a single comprehensive title report. When combining:
        
        1. Integrate all information from all reports
        2. Maintain chronological order in the chain of title
        3. Add any new information about property identification, ownership, encumbrances, etc.
        4. If there are conflicts between reports, note them explicitly
        5. Preserve the comprehensive structure of the report
        6. Ensure no details from any report are omitted
        7. Create comprehensive conclusions and recommendations based on all documents

        FORMAT REQUIREMENTS:
        - Begin with a clear title and date of report
        - Use numbered sections with clear headings
        - Present the chain of title as a detailed chronological table
        - For entries with extensive details, provide complete information rather than summarizing
        - Bold key facts, dates, and figures
        - Ensure ALL information is directly extracted from the documents
        - If information appears to be missing or unclear, explicitly note this

        Produce a comprehensive, consolidated report that incorporates ALL information from ALL reports.
        """
        
        system_message = "You are an expert legal title examiner with decades of experience in property law, land records, and title searches. You meticulously extract EVERY detail from land records to create exhaustive title reports that document the complete chain of title without omitting any information. Your specialty is creating detailed chronological ownership histories that capture every entry in land records without summarization."
        
        # Call Groq API with retry mechanism
        max_retries = 3
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending combination request to Groq API (attempt {attempt + 1}/{max_retries})")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=8000,
                    temperature=0.0  # Zero temperature for factual accuracy
                )
                
                # Update rate limiting history
                self._update_request_history()
                
                logger.info(f"Reports combined successfully. Tokens: {response.usage.total_tokens}")
                return response.choices[0].message.content
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"API call failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed: {str(e)}")
                    raise
    
    async def analyze_documents(self, document_texts: List[str]) -> str:
        """
        Process each document individually and then combine the reports
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            Structured consolidated title report
        """
        if not document_texts:
            logger.warning("No document texts provided for analysis")
            return "Error: No documents provided for analysis."
            
        logger.info(f"Processing {len(document_texts)} documents individually")
        
        try:
            # Process each document individually
            individual_reports = []
            processing_errors = []
            
            for i, doc_text in enumerate(document_texts):
                try:
                    logger.info(f"Processing document {i+1}/{len(document_texts)}")
                    report = await self.process_single_document(doc_text, i+1)
                    
                    # Check if report indicates an error
                    if report.startswith("ERROR:"):
                        processing_errors.append(f"Document {i+1}: {report}")
                        logger.warning(f"Error processing document {i+1}: {report}")
                    else:
                        individual_reports.append(report)
                        logger.info(f"Document {i+1}/{len(document_texts)} processed successfully")
                        
                except Exception as e:
                    error_msg = f"Error processing document {i+1}: {str(e)}"
                    processing_errors.append(error_msg)
                    logger.error(error_msg)
            
            # If we didn't process any documents successfully, return error
            if not individual_reports:
                error_summary = "\n".join(processing_errors)
                return f"Failed to process any documents successfully:\n{error_summary}"
            
            # Combine all reports into one
            logger.info(f"Combining {len(individual_reports)} individual reports")
            combined_report = await self.combine_reports(individual_reports)
            
            # If there were any errors, append them to the report
            if processing_errors:
                error_summary = "\n".join(processing_errors)
                combined_report += f"\n\n## PROCESSING ERRORS\nThe following errors occurred during processing:\n{error_summary}"
            
            logger.info("Report generation completed successfully")
            return combined_report
            
        except Exception as e:
            logger.error(f"Error during document analysis: {str(e)}")
            return f"Error analyzing documents: {str(e)}"