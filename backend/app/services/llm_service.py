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
        
        # Rate limiting settings - updated for Groq's actual limits
        self.requests_per_minute = 10
        self.token_limit_per_minute = 50000  # Enhanced from 6000 to 50000 tokens
        self.token_limit_per_request = 8000  # Maximum tokens per request
        
        # Track both request and token history for rate limiting
        self.token_history = deque()  # Stores (timestamp, token_count) tuples
        self.request_history = deque()  # Stores timestamps of requests
        self.window_size_seconds = 60  # 1 minute window
        
        logger.info(f"LLMService initialized with model {self.model}, limits: {self.requests_per_minute} requests/minute, "
                   f"{self.token_limit_per_minute} tokens/minute, and {self.token_limit_per_request} tokens/request")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Roughly estimate the number of tokens in the text.
        For GPT models, ~4 chars ≈ 1 token, but this is a simple approximation.
        """
        return len(text) // 4
    
    def _update_rate_history(self, tokens_used: int) -> None:
        """
        Update both token and request history
        """
        current_time = time.time()
        
        # Update token history
        self.token_history.append((current_time, tokens_used))
        while self.token_history and self.token_history[0][0] < current_time - self.window_size_seconds:
            self.token_history.popleft()
        
        # Update request history
        self.request_history.append(current_time)
        while self.request_history and self.request_history[0] < current_time - self.window_size_seconds:
            self.request_history.popleft()
        
        current_token_usage = self._get_current_token_usage()
        current_request_usage = len(self.request_history)
        
        logger.debug(f"Rate limits: {current_request_usage}/{self.requests_per_minute} requests, "
                    f"{current_token_usage}/{self.token_limit_per_minute} tokens in current window")
    
    def _get_current_token_usage(self) -> int:
        """
        Calculate total tokens used in the current time window
        """
        return sum(tokens for _, tokens in self.token_history)
    
    def _check_rate_limit(self, estimated_tokens: int) -> float:
        """
        Check if we would exceed any rate limit (requests or tokens)
        Returns wait time in seconds, or 0 if no wait needed
        """
        current_time = time.time()
        
        # Clean up old entries
        while self.token_history and self.token_history[0][0] < current_time - self.window_size_seconds:
            self.token_history.popleft()
            
        while self.request_history and self.request_history[0] < current_time - self.window_size_seconds:
            self.request_history.popleft()
        
        # Check request limit (usually more restrictive than token limit)
        current_requests = len(self.request_history)
        current_tokens = self._get_current_token_usage()
        
        logger.debug(f"Current usage: {current_requests}/{self.requests_per_minute} requests, "
                   f"{current_tokens}/{self.token_limit_per_minute} tokens")
        
        if current_requests >= self.requests_per_minute:
            # Request limit reached
            oldest_request = self.request_history[0]
            time_to_wait = (oldest_request + self.window_size_seconds) - current_time
            wait_time = max(0, time_to_wait + 0.1)  # Add small buffer
            
            if wait_time > 0:
                logger.info(f"Request rate limit reached. Waiting {wait_time:.2f}s before processing. "
                          f"Current usage: {current_requests}/{self.requests_per_minute} requests")
            
            return wait_time
            
        if current_tokens + estimated_tokens > self.token_limit_per_minute:
            # Token limit reached
            oldest_token_time = self.token_history[0][0]
            time_to_wait = (oldest_token_time + self.window_size_seconds) - current_time
            wait_time = max(0, time_to_wait + 0.1)  # Add small buffer
            
            if wait_time > 0:
                logger.info(f"Token rate limit would be exceeded. Waiting {wait_time:.2f}s before processing. "
                          f"Current usage: {current_tokens}/{self.token_limit_per_minute} tokens")
            
            return wait_time
            
        return 0  # No wait needed
    
    async def process_single_document(self, doc_text: str, doc_index: int) -> str:
        """
        Process a single document and generate a report
        
        Args:
            doc_text: Text content of the document
            doc_index: Index of the document (for logging)
            
        Returns:
            Title report for this document
        """
        # Check document size
        estimated_tokens = self._estimate_tokens(doc_text)
        if estimated_tokens > self.token_limit_per_request * 0.6:
            logger.warning(f"Document {doc_index} too large ({estimated_tokens} est. tokens)")
            return f"ERROR: Document {doc_index} exceeds token limits with approximately {estimated_tokens} tokens."
        
        # Check rate limit
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            logger.info(f"Waiting {wait_time:.2f}s before processing document {doc_index} due to rate limits")
            await asyncio.sleep(wait_time)
        
        # Modified prompt to avoid template issues
        prompt = f"""
        Analyze the following property document to generate a detailed title report. Extract all key information.

        ## Document Content:
        {doc_text}

        ## Instructions:
        Create a comprehensive title report with the following sections:
        
        1. Basic Property Identification (survey numbers, location)
        2. Area and Assessment details
        3. Current Ownership information
        4. Chronological Chain of Title (as a detailed table)
        5. Land Status Changes
        6. Encumbrances and Litigation
        7. Rights and Restrictions
        8. Revenue and Tax Status
        9. Other relevant information
        10. Conclusion and Recommendations

        IMPORTANT FORMATTING INSTRUCTIONS:
        - Include ONLY information that is actually present in the document
        - Use actual data extracted from the document
        - If information is not available, state "Not specified in document" rather than using placeholders
        - Bold key facts, dates, and figures
        - For the Chain of Title table, use markdown table format
        - Be specific and precise - include actual names, dates, and amounts from the document
        - DO NOT use placeholder text like "[Insert X]" or "[Insert date]"
        - DO NOT create a template - this should be a final report with actual content

        Your response should be a complete, ready-to-read report with real content, not a template.
        """
        
        system_message = "You are an expert legal title examiner with decades of experience in property law and land records. Your task is to extract all relevant details from property documents and create comprehensive title reports with actual content, not templates or placeholders."
        
        # Call Groq API with retry mechanism and detailed error handling
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
                    temperature=0.0
                )
                
                # Log complete response details for debugging
                content = response.choices[0].message.content
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                
                # Log first part of response for debugging
                logger.debug(f"Raw API response preview for document {doc_index}: {content[:500]}...")
                
                # Check if response is empty or contains only placeholders
                if not content or content.strip() == "":
                    logger.warning(f"Document {doc_index} generated an empty response")
                    if attempt < max_retries - 1:
                        logger.info("Retrying with modified prompt...")
                        continue
                    return "ERROR: Unable to generate a meaningful report from this document. The response was empty."
                
                if "[Insert" in content:
                    logger.warning(f"Document {doc_index} response contains placeholder text")
                    if attempt < max_retries - 1:
                        # Add more specific instructions to avoid placeholders for the retry
                        prompt += "\n\nIMPORTANT: Your response contains placeholder text like '[Insert X]'. DO NOT use ANY placeholders. Only include actual information from the document or explicitly state 'Information not available in document'."
                        logger.info("Retrying with stronger instructions against placeholders...")
                        continue
                    else:
                        # Replace placeholders with better text
                        content = content.replace("[Insert date]", "Date not specified in document")
                        content = content.replace("[Insert", "Not specified in document (")
                        content = content.replace("]", ")")
                
                # Update rate history
                self._update_rate_history(tokens_used)
                
                logger.info(f"Document {doc_index} processed successfully. Content length: {len(content)} chars, Tokens used: {tokens_used}")
                return content
                
            except Exception as e:
                error_message = str(e)
                
                # Extract status code if available
                status_code = None
                if hasattr(e, 'status_code'):
                    status_code = e.status_code
                elif hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                    status_code = e.response.status_code
                    
                logger.error(f"API call failed with status code {status_code}: {error_message}")
                
                # Check for specific error types
                if "context_length_exceeded" in error_message:
                    return f"ERROR: Document {doc_index} exceeds context length limits. Please split this document into smaller parts."
                elif "rate_limit_exceeded" in error_message:
                    if attempt < max_retries - 1:
                        wait_time = 60 if "minute" in error_message else backoff_factor ** attempt
                        logger.warning(f"Rate limit exceeded. Waiting {wait_time}s before retrying...")
                        await asyncio.sleep(wait_time)
                    else:
                        return f"ERROR: Rate limit exceeded for document {doc_index}. Please try again later."
                elif attempt < max_retries - 1:
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed for document {doc_index}")
                    return f"ERROR: Failed to process document {doc_index}: {error_message}"
    
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
        
        # Check for error reports and remove them from content to combine
        filtered_reports = []
        error_messages = []
        
        for i, report in enumerate(reports):
            if report.startswith("ERROR:"):
                error_messages.append(f"Document {i+1}: {report}")
            else:
                filtered_reports.append(report)
        
        if not filtered_reports:
            error_summary = "\n".join(error_messages)
            return f"Failed to generate a combined report. All individual reports contained errors:\n{error_summary}"
        
        # Check rate limit before combining
        wait_time = self._check_rate_limit(5000)  # Conservative estimate
        if wait_time > 0:
            logger.info(f"Waiting {wait_time:.2f}s before combining reports due to rate limits")
            await asyncio.sleep(wait_time)
        
        # Prepare individual reports for combining
        report_sections = []
        for i, report in enumerate(filtered_reports):
            # Process each report to extract the most important information
            # Limit size to avoid token limits
            max_chars = 3000  # Approximately 750 tokens per report
            summary = report[:max_chars]
            if len(report) > max_chars:
                summary += "... [truncated for combination]"
            report_sections.append(f"--- REPORT {i+1} ---\n{summary}\n")
        
        combined_reports = "\n\n".join(report_sections)
        
        prompt = f"""
        You have analyzed multiple property documents and generated individual reports.
        Now, combine these reports into a single comprehensive title report.

        ## Individual Reports:
        {combined_reports}

        ## Instructions:
        Create a unified report that consolidates all information from these individual reports. 
        
        IMPORTANT:
        - DO NOT use placeholder text like "[Insert X]" or "[Insert date]"
        - Only include actual information from the individual reports
        - If information is not available, state "Not specified in the documents"
        - Indicate which document number (Report 1, Report 2, etc.) information comes from when combining
        - Resolve conflicts by stating both pieces of information and their sources
        - Bold key facts, dates, and figures
        - For the Chain of Title, create a comprehensive chronological table
        
        Your combined report must be a final product with actual content, not a template.
        """
        
        system_message = "You are an expert legal title examiner tasked with consolidating multiple property reports into a comprehensive analysis. Create reports with actual content, never placeholders or templates."
        
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
                    temperature=0.0
                )
                
                # Get the combined report content
                combined_report = response.choices[0].message.content
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                
                # Log preview of combined report
                logger.debug(f"Combined report preview: {combined_report[:500]}...")
                
                # Check for empty response
                if not combined_report or combined_report.strip() == "":
                    logger.error("Combined report is empty or blank")
                    if attempt < max_retries - 1:
                        logger.info("Retrying combination with simplified prompt...")
                        continue
                    return "ERROR: Generated combined report was empty. Please check individual reports for content."
                
                # Check for placeholder text
                if "[Insert" in combined_report:
                    logger.warning("Combined report contains placeholder text")
                    if attempt < max_retries - 1:
                        # Add more specific instructions for retry
                        prompt += "\n\nCRITICAL: Your response contains placeholder text like '[Insert X]'. DO NOT use ANY placeholders. Only include actual information or explicitly state 'Information not available'."
                        logger.info("Retrying combination with stronger instructions against placeholders...")
                        continue
                    else:
                        # Fix placeholders in final output
                        combined_report = combined_report.replace("[Insert date]", "Date not specified in documents")
                        combined_report = combined_report.replace("[Insert", "Not specified in documents (")
                        combined_report = combined_report.replace("]", ")")
                
                # Update rate limiting history
                self._update_rate_history(tokens_used)
                
                # Append any error messages if there were some
                if error_messages:
                    error_summary = "\n".join(error_messages)
                    combined_report += f"\n\n## PROCESSING ERRORS\nThe following errors occurred during processing:\n{error_summary}"
                
                logger.info(f"Reports combined successfully. Tokens: {tokens_used}")
                return combined_report
                
            except Exception as e:
                error_message = str(e)
                
                # Extract status code if available
                status_code = None
                if hasattr(e, 'status_code'):
                    status_code = e.status_code
                elif hasattr(e, 'response') and hasattr(e.response, 'status_code'):
                    status_code = e.response.status_code
                    
                logger.error(f"API call failed with status code {status_code}: {error_message}")
                
                if "context_length_exceeded" in error_message:
                    # Try with fewer reports
                    logger.warning("Context length exceeded when combining reports. Trying with reduced content...")
                    if attempt < max_retries - 1:
                        # Reduce the amount of content per report
                        max_chars = max_chars // 2
                        continue
                    else:
                        return "ERROR: Unable to combine reports due to context length limitations. Please combine fewer reports at a time."
                        
                elif attempt < max_retries - 1:
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("All retry attempts failed for report combination")
                    return f"ERROR: Failed to combine reports: {error_message}"
    
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
            
            # If there were any errors not already included, append them to the report
            if processing_errors and not combined_report.endswith(processing_errors[-1]):
                error_summary = "\n".join(processing_errors)
                combined_report += f"\n\n## PROCESSING ERRORS\nThe following errors occurred during processing:\n{error_summary}"
            
            logger.info("Report generation completed successfully")
            return combined_report
            
        except Exception as e:
            logger.error(f"Error during document analysis: {str(e)}")
            return f"Error analyzing documents: {str(e)}"