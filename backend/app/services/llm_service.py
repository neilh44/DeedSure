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
        self.token_limit_per_minute = 5500
        self.token_limit_per_request = 6000  # New per-request token limit
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
    
    def _split_documents_into_batches(self, document_texts: List[str]) -> List[List[str]]:
        """
        Split documents into batches to ensure each batch stays under the token limit
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            List of document batches, where each batch is a list of document texts
        """
        batches = []
        current_batch = []
        current_batch_tokens = 0
        system_message = "You are a specialized legal assistant with expertise in property law and title searches."
        
        # Reserve tokens for system message and prompt template (approximately)
        prompt_template_tokens = self._estimate_tokens("""
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
            [rest of template]
        """)
        
        # Reserve tokens for the system message and prompt template
        reserved_tokens = self._estimate_tokens(system_message) + prompt_template_tokens
        # Set a max token count for documents in a single batch
        max_batch_tokens = self.token_limit_per_request - reserved_tokens - 500  # 500 token buffer
        
        for doc in document_texts:
            doc_tokens = self._estimate_tokens(doc)
            
            # If a single document is too big to fit in one batch, we need to split it
            if doc_tokens > max_batch_tokens:
                logger.warning(f"Document too large ({doc_tokens} est. tokens). Consider preprocessing to split large documents.")
                # If there are documents in the current batch, add them as a batch first
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_batch_tokens = 0
                
                # Add this large document as its own batch
                # In a more advanced implementation, you might split the document itself
                batches.append([doc])
                continue
                
            # If adding this document would exceed the batch token limit
            if current_batch_tokens + doc_tokens > max_batch_tokens and current_batch:
                batches.append(current_batch)
                current_batch = [doc]
                current_batch_tokens = doc_tokens
            else:
                current_batch.append(doc)
                current_batch_tokens += doc_tokens
        
        # Add the last batch if not empty
        if current_batch:
            batches.append(current_batch)
            
        logger.info(f"Split {len(document_texts)} documents into {len(batches)} batches")
        return batches
    
    async def _process_batch(self, batch: List[str]) -> str:
        """
        Process a single batch of documents
        
        Args:
            batch: List of document text contents for this batch
            
        Returns:
            Analysis result for this batch
        """
        combined_text = "\n\n---DOCUMENT SEPARATOR---\n\n".join(batch)
        
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
        
        # Estimate tokens for this request (prompt + system message)
        system_message = "You are a specialized legal assistant with expertise in property law and title searches."
        estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
        
        logger.debug(f"Estimated token usage for batch request: {estimated_tokens}")
        
        if estimated_tokens > self.token_limit_per_request:
            logger.warning(f"Batch exceeds token limit ({estimated_tokens} > {self.token_limit_per_request}). Consider reducing batch size.")
        
        # Check rate limit
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            # Wait until we can process this request
            logger.info(f"Rate limit reached. Waiting {wait_time:.2f}s before sending request.")
            await asyncio.sleep(wait_time)  # Using asyncio.sleep for async compatibility
        
        # Call Groq API with retry mechanism
        max_retries = 3
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending batch request to Groq API (attempt {attempt + 1}/{max_retries})")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=8000,
                    temperature=0.2
                )
                
                # Update token history with actual tokens used
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                self._update_token_history(tokens_used)
                
                logger.info(f"Batch analysis completed. Tokens used: {tokens_used}")
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
        Send documents to LLM for title report generation with rate limiting and batching
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            Structured title report text
        """
        if not document_texts:
            logger.warning("No document texts provided for analysis")
            return "Error: No documents provided for analysis."
            
        logger.info(f"Analyzing {len(document_texts)} documents with LLM using batching")
        
        try:
            # Split documents into batches
            batches = self._split_documents_into_batches(document_texts)
            
            if len(batches) == 1:
                # If there's only one batch, process it directly
                return await self._process_batch(batches[0])
            else:
                # For multiple batches, process each and combine results
                batch_results = []
                
                for i, batch in enumerate(batches):
                    logger.info(f"Processing batch {i+1}/{len(batches)} with {len(batch)} documents")
                    result = await self._process_batch(batch)
                    batch_results.append(result)
                
                # Now we need to combine the results
                # For a title report, we might need a separate processing step
                combined_report = await self._combine_batch_reports(batch_results)
                return combined_report
                
        except Exception as e:
            logger.error(f"Error during document analysis: {str(e)}")
            return f"Error analyzing documents: {str(e)}"
    
    async def _combine_batch_reports(self, batch_results: List[str]) -> str:
        """
        Combine multiple batch results into a single coherent report
        
        Args:
            batch_results: List of analysis results from each batch
            
        Returns:
            Combined report
        """
        logger.info(f"Combining {len(batch_results)} batch results into a single report")
        
        # If there are many batch results, we might need to batch this combination as well
        if len(batch_results) == 1:
            return batch_results[0]
            
        combined_text = "\n\n---REPORT SEPARATOR---\n\n".join(batch_results)
        
        prompt = f"""
        You are a specialized legal assistant with expertise in property law and title searches.
        
        You've been given multiple separate title reports that need to be consolidated into a single comprehensive report.
        These reports may contain overlapping information or refer to different aspects of the same property or related properties.
        
        ## Instructions:
        1. Consolidate all information into a single coherent title report
        2. Ensure chronological order in the chain of title
        3. Remove duplicate information
        4. Harmonize any conflicting information, noting discrepancies if significant
        5. Maintain the standardized title report format
        
        ## Report Fragments:
        {combined_text}
        
        Please produce a single consolidated title report that incorporates all relevant information from these fragments.
        """
        
        system_message = "You are a specialized legal assistant with expertise in property law and title searches."
        estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
        
        # If the combined report would be too large, we need a different approach
        if estimated_tokens > self.token_limit_per_request:
            logger.warning(f"Combined report would exceed token limit ({estimated_tokens} > {self.token_limit_per_request})")
            return "The property documents require a more extensive analysis than can be provided in a single report. Please review the separate batch reports or contact support for assistance."
        
        # Check rate limit
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            logger.info(f"Rate limit reached. Waiting {wait_time:.2f}s before consolidating reports.")
            await asyncio.sleep(wait_time)
        
        # Use the same retry mechanism as in the batch processing
        max_retries = 3
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending consolidation request to Groq API (attempt {attempt + 1}/{max_retries})")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=8000,
                    temperature=0.2
                )
                
                # Update token history
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                self._update_token_history(tokens_used)
                
                logger.info(f"Report consolidation completed. Tokens used: {tokens_used}")
                return response.choices[0].message.content
                
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"API call failed: {str(e)}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed: {str(e)}")
                    raise