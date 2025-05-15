import asyncio
from typing import Dict, Any, List, Optional, Tuple
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
        self.token_limit_per_request = 6000  # Enforced max tokens per request
        self.token_history = deque()  # Stores (timestamp, token_count) tuples
        self.window_size_seconds = 60  # 1 minute window
        
        # Document processing settings
        self.max_document_chunk_size = 4000  # Max tokens for a document chunk
        self.max_batch_document_tokens = 4000  # Max total document tokens per batch
        
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
    
    def _chunk_document(self, document: str) -> List[str]:
        """
        Split a large document into smaller chunks that fit within token limits
        
        Args:
            document: Document text content
            
        Returns:
            List of document chunks
        """
        doc_tokens = self._estimate_tokens(document)
        
        if doc_tokens <= self.max_document_chunk_size:
            return [document]
            
        logger.info(f"Chunking large document ({doc_tokens} est. tokens) into smaller parts")
        
        # Split by paragraphs first
        paragraphs = document.split("\n\n")
        chunks = []
        current_chunk = []
        current_chunk_tokens = 0
        
        for paragraph in paragraphs:
            para_tokens = self._estimate_tokens(paragraph)
            
            # If a single paragraph is too large, split it by sentences
            if para_tokens > self.max_document_chunk_size:
                logger.warning(f"Large paragraph found ({para_tokens} tokens). Splitting by sentences.")
                sentences = paragraph.replace('. ', '.\n').split('\n')
                
                for sentence in sentences:
                    sent_tokens = self._estimate_tokens(sentence)
                    
                    # If adding this sentence would exceed the chunk size, create a new chunk
                    if current_chunk_tokens + sent_tokens > self.max_document_chunk_size and current_chunk:
                        chunks.append("\n\n".join(current_chunk))
                        current_chunk = [sentence]
                        current_chunk_tokens = sent_tokens
                    else:
                        current_chunk.append(sentence)
                        current_chunk_tokens += sent_tokens
            
            # Handle paragraph that fits within limit
            elif current_chunk_tokens + para_tokens > self.max_document_chunk_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [paragraph]
                current_chunk_tokens = para_tokens
            else:
                current_chunk.append(paragraph)
                current_chunk_tokens += para_tokens
        
        # Add the last chunk if not empty
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
        
        logger.info(f"Document chunked into {len(chunks)} parts")
        return chunks
    
    def _prepare_batches(self, document_texts: List[str]) -> List[List[str]]:
        """
        Process documents and create batches that respect token limits
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            List of document batches, where each batch is a list of document text chunks
        """
        # First, split large documents into chunks
        all_chunks = []
        for doc in document_texts:
            chunks = self._chunk_document(doc)
            all_chunks.extend(chunks)
        
        # Calculate estimated prompt overhead tokens (system message + template)
        system_message = "You are a specialized legal assistant with expertise in property law and title searches."
        prompt_template = """
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
        [template content]
        """
        
        overhead_tokens = self._estimate_tokens(system_message) + self._estimate_tokens(prompt_template)
        # Add buffer for API overhead and response
        safety_buffer = 500
        max_chunk_tokens_per_batch = self.token_limit_per_request - overhead_tokens - safety_buffer
        
        # Now create batches from the chunks
        batches = []
        current_batch = []
        current_batch_tokens = 0
        
        for chunk in all_chunks:
            chunk_tokens = self._estimate_tokens(chunk)
            
            # Verify each chunk is within limits
            if chunk_tokens > max_chunk_tokens_per_batch:
                logger.warning(f"Chunk still too large ({chunk_tokens} tokens) even after splitting. " +
                             f"Truncating to {max_chunk_tokens_per_batch} tokens.")
                # Truncate the chunk if it's still too large
                chunk = chunk[:max_chunk_tokens_per_batch * 4]  # Approximate chars to tokens
                chunk_tokens = self._estimate_tokens(chunk)
            
            # If adding this chunk would exceed the batch token limit
            if current_batch_tokens + chunk_tokens > max_chunk_tokens_per_batch and current_batch:
                batches.append(current_batch)
                current_batch = [chunk]
                current_batch_tokens = chunk_tokens
            else:
                current_batch.append(chunk)
                current_batch_tokens += chunk_tokens
        
        # Add the last batch if not empty
        if current_batch:
            batches.append(current_batch)
            
        logger.info(f"Created {len(batches)} batches from {len(all_chunks)} document chunks")
        
        # Verify all batches are within token limits
        for i, batch in enumerate(batches):
            batch_text = "\n\n---DOCUMENT SEPARATOR---\n\n".join(batch)
            batch_tokens = self._estimate_tokens(batch_text) + overhead_tokens
            
            if batch_tokens > self.token_limit_per_request:
                logger.warning(f"Batch {i+1} exceeds token limit ({batch_tokens} tokens). Adjusting...")
                # This should not happen with proper chunking, but as a safety measure,
                # recreate this batch with fewer chunks
                new_batch = []
                new_batch_tokens = 0
                
                for chunk in batch:
                    chunk_tokens = self._estimate_tokens(chunk)
                    if new_batch_tokens + chunk_tokens + overhead_tokens <= self.token_limit_per_request:
                        new_batch.append(chunk)
                        new_batch_tokens += chunk_tokens
                    else:
                        # This chunk doesn't fit, start a new batch
                        break
                
                if new_batch:
                    batches[i] = new_batch
                    # Handle remaining chunks in the future
                else:
                    logger.error(f"Failed to create valid batch. First chunk too large.")
                    # Keep just the first chunk but truncate it
                    if batch:
                        first_chunk = batch[0]
                        max_chars = (self.token_limit_per_request - overhead_tokens - safety_buffer) * 4
                        truncated_chunk = first_chunk[:max_chars]
                        batches[i] = [truncated_chunk]
        
        return batches
    
    async def _process_batch(self, batch: List[str]) -> Tuple[str, bool]:
        """
        Process a single batch of document chunks
        
        Args:
            batch: List of document text chunks for this batch
            
        Returns:
            Tuple of (analysis result, success flag)
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
            logger.error(f"Batch exceeds token limit ({estimated_tokens} > {self.token_limit_per_request}) even after preprocessing.")
            return f"Error: Document too large to process within token limits ({estimated_tokens} tokens).", False
        
        # Check rate limit
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            logger.info(f"Rate limit reached. Waiting {wait_time:.2f}s before sending request.")
            await asyncio.sleep(wait_time)
        
        # Call Groq API with retry mechanism
        max_retries = 3
        backoff_factor = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending batch request to Groq API (attempt {attempt + 1}/{max_retries})")
                
                # Limit tokens in both directions
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000,  # Limit the response size
                    temperature=0.2
                )
                
                # Update token history with actual tokens used
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                self._update_token_history(tokens_used)
                
                logger.info(f"Batch analysis completed. Tokens used: {tokens_used}")
                return response.choices[0].message.content, True
                
            except Exception as e:
                error_message = str(e)
                
                # Check for token limit exceeded errors specifically
                if "413" in error_message and "too large" in error_message:
                    logger.error(f"Request too large for API: {error_message}")
                    if attempt == max_retries - 1:
                        # This is the last attempt, return error
                        return f"Error: Unable to process document due to size constraints. Please break down the document into smaller parts.", False
                    else:
                        # Reduce prompt size for next attempt by truncating the document content
                        logger.warning(f"Reducing content size for next attempt")
                        # Cut the batch in half for the next attempt
                        if len(batch) > 1:
                            batch = batch[:len(batch)//2]
                        else:
                            # If only one chunk, truncate it
                            batch[0] = batch[0][:len(batch[0])//2]
                        combined_text = "\n\n---DOCUMENT SEPARATOR---\n\n".join(batch)
                        prompt = prompt.replace("{combined_text}", combined_text)
                        estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
                        logger.info(f"Reduced content size, new token estimate: {estimated_tokens}")
                elif attempt < max_retries - 1:
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"API call failed: {error_message}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed: {error_message}")
                    return f"Error processing documents: {error_message}", False
    
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
            # Prepare batches with proper chunking
            batches = self._prepare_batches(document_texts)
            
            if not batches:
                return "Error: Failed to prepare document batches for processing."
            
            if len(batches) == 1:
                # If there's only one batch, process it directly
                result, success = await self._process_batch(batches[0])
                return result
            else:
                # For multiple batches, process each and combine results
                batch_results = []
                all_succeeded = True
                
                for i, batch in enumerate(batches):
                    logger.info(f"Processing batch {i+1}/{len(batches)} with {len(batch)} chunks")
                    result, success = await self._process_batch(batch)
                    if success:
                        batch_results.append(result)
                    else:
                        all_succeeded = False
                        batch_results.append(f"Batch {i+1} analysis failed: {result}")
                
                # Now we need to combine the results
                # Only attempt to combine if we have some successful results
                if batch_results and any(not r.startswith("Error") and not r.startswith("Batch") for r in batch_results):
                    combined_report = await self._combine_batch_reports(batch_results)
                    return combined_report
                elif not all_succeeded:
                    return "Error: Failed to process one or more document batches. Please review the individual errors or try with smaller documents."
                else:
                    return "Error: No successful document analysis to report."
                
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
        
        # If the combined report would be too large, we need to process it in batches too
        if estimated_tokens > self.token_limit_per_request:
            logger.warning(f"Combined report would exceed token limit ({estimated_tokens} > {self.token_limit_per_request})")
            
            # Split the batch results into smaller groups
            max_batch_results = 3  # Process 3 results at a time
            result_batches = [batch_results[i:i+max_batch_results] for i in range(0, len(batch_results), max_batch_results)]
            
            intermediate_results = []
            for i, result_batch in enumerate(result_batches):
                logger.info(f"Processing intermediate combination batch {i+1}/{len(result_batches)}")
                batch_text = "\n\n---REPORT SEPARATOR---\n\n".join(result_batch)
                
                intermediate_prompt = prompt.replace("{combined_text}", batch_text)
                estimated_tokens = self._estimate_tokens(intermediate_prompt) + self._estimate_tokens(system_message)
                
                if estimated_tokens > self.token_limit_per_request:
                    logger.warning(f"Intermediate batch still too large ({estimated_tokens} tokens). Using first result only.")
                    intermediate_results.append(result_batch[0])
                    continue
                
                # Process this intermediate batch
                wait_time = self._check_rate_limit(estimated_tokens)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
                
                try:
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": intermediate_prompt}
                        ],
                        max_tokens=4000,
                        temperature=0.2
                    )
                    
                    tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                    self._update_token_history(tokens_used)
                    
                    intermediate_results.append(response.choices[0].message.content)
                except Exception as e:
                    logger.error(f"Error combining intermediate results: {str(e)}")
                    # If combination fails, just use the first result from this batch
                    if result_batch:
                        intermediate_results.append(result_batch[0])
            
            # Now combine the intermediate results
            if len(intermediate_results) == 1:
                return intermediate_results[0]
            else:
                return await self._combine_batch_reports(intermediate_results)
        
        # Standard processing for reports that fit within limits
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
                    max_tokens=4000,
                    temperature=0.2
                )
                
                # Update token history
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                self._update_token_history(tokens_used)
                
                logger.info(f"Report consolidation completed. Tokens used: {tokens_used}")
                return response.choices[0].message.content
                
            except Exception as e:
                error_message = str(e)
                
                # Check for token limit exceeded errors
                if "413" in error_message and "too large" in error_message:
                    logger.error(f"Consolidation request too large: {error_message}")
                    if attempt == max_retries - 1:
                        # On last attempt, return a simple combination
                        return "## CONSOLIDATED TITLE REPORT\n\nThis report combines multiple analyses due to document size.\n\n" + \
                               "\n\n---SECTION DIVIDER---\n\n".join(batch_results[:3]) + \
                               "\n\n(Some sections may have been omitted due to size constraints.)"
                elif attempt < max_retries - 1:
                    wait_time = backoff_factor ** attempt
                    logger.warning(f"API call failed: {error_message}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed: {error_message}")
                    return "## CONSOLIDATED TITLE REPORT\n\nDue to processing limitations, here are the key sections of the report:\n\n" + \
                           "\n\n---SECTION DIVIDER---\n\n".join(batch_results[:2])