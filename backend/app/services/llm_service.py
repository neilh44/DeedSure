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
        
        # CRITICAL: LLaMA-3-8b-8192 has a context window of only 2048 tokens
        self.model_context_window = 2048
        
        # Document processing settings - significantly reduced for smaller context window
        self.max_document_chunk_size = 800  # Very small chunk size
        
        # Reserve tokens for system message, prompt, and response
        # With 2048 token context window, we need to be very conservative
        self.max_input_tokens = 1200  # Reserve ~800 tokens for prompt overhead and response
        
        logger.info(f"LLMService initialized with model {self.model}, token limit {self.token_limit_per_minute}/minute, " +
                  f"{self.token_limit_per_request}/request, and context window {self.model_context_window}")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Roughly estimate the number of tokens in the text.
        For LLaMA models, ~3.5 chars ≈ 1 token, but this is a simple approximation.
        Using a slightly more conservative ratio to avoid underestimating.
        """
        return len(text) // 3
    
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
        Split a large document into very small chunks to fit within 2048 token context window
        
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
        
        # If very few paragraphs, try to split by sentences
        if len(paragraphs) < 3:
            paragraphs = []
            for para in document.split("\n\n"):
                paragraphs.extend(para.replace('. ', '.\n').split('\n'))
        
        chunks = []
        current_chunk = []
        current_chunk_tokens = 0
        
        for paragraph in paragraphs:
            para_tokens = self._estimate_tokens(paragraph)
            
            # If a single paragraph is too large, split it by sentences
            if para_tokens > self.max_document_chunk_size:
                sentences = paragraph.replace('. ', '.\n').split('\n')
                
                for sentence in sentences:
                    sent_tokens = self._estimate_tokens(sentence)
                    
                    # If even a single sentence is too long, truncate it into smaller pieces
                    if sent_tokens > self.max_document_chunk_size:
                        logger.warning(f"Very long sentence found ({sent_tokens} tokens). Splitting into smaller segments.")
                        # Use an even smaller segment size to ensure they fit
                        segment_size = self.max_document_chunk_size * 2  # chars, not tokens
                        segments = [sentence[i:i + segment_size] for i in range(0, len(sentence), segment_size)]
                        
                        for segment in segments:
                            seg_tokens = self._estimate_tokens(segment)
                            if current_chunk_tokens + seg_tokens > self.max_document_chunk_size and current_chunk:
                                chunks.append("\n".join(current_chunk))
                                current_chunk = [segment]
                                current_chunk_tokens = seg_tokens
                            else:
                                current_chunk.append(segment)
                                current_chunk_tokens += seg_tokens
                        continue
                    
                    # For normal sentences
                    if current_chunk_tokens + sent_tokens > self.max_document_chunk_size and current_chunk:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [sentence]
                        current_chunk_tokens = sent_tokens
                    else:
                        current_chunk.append(sentence)
                        current_chunk_tokens += sent_tokens
            
            # Handle regular paragraphs
            elif current_chunk_tokens + para_tokens > self.max_document_chunk_size and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = [paragraph]
                current_chunk_tokens = para_tokens
            else:
                current_chunk.append(paragraph)
                current_chunk_tokens += para_tokens
        
        # Add the last chunk if not empty
        if current_chunk:
            chunks.append("\n".join(current_chunk))
        
        logger.info(f"Document chunked into {len(chunks)} parts")
        return chunks
    
    def _prepare_batches(self, document_texts: List[str]) -> List[List[str]]:
        """
        Process documents and create small batches that fit in 2048 token context window
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            List of document batches, where each batch is a list of document text chunks
        """
        # First, split documents into small chunks
        all_chunks = []
        for doc in document_texts:
            chunks = self._chunk_document(doc)
            all_chunks.extend(chunks)
        
        # Use a minimal prompt template to conserve tokens
        system_message = "You are a legal assistant."
        prompt_template = """
        Analyze this legal document excerpt and identify:
        - Property details
        - Ownership information
        - Key dates
        
        Document:
        {combined_text}
        """
        
        overhead_tokens = self._estimate_tokens(system_message) + self._estimate_tokens(prompt_template)
        safety_buffer = 100
        max_chunk_tokens_per_batch = self.max_input_tokens - overhead_tokens - safety_buffer
        
        # Create small batches
        batches = []
        current_batch = []
        current_batch_tokens = 0
        
        for chunk in all_chunks:
            chunk_tokens = self._estimate_tokens(chunk)
            
            # In this extremely constrained context window, most chunks will need their own batch
            # Only combine very small chunks together
            if current_batch_tokens + chunk_tokens > max_chunk_tokens_per_batch and current_batch:
                batches.append(current_batch)
                current_batch = [chunk]
                current_batch_tokens = chunk_tokens
            else:
                current_batch.append(chunk)
                current_batch_tokens += chunk_tokens
                
                # If we've added a chunk and we're close to the limit, create a new batch
                if current_batch_tokens > max_chunk_tokens_per_batch * 0.8:
                    batches.append(current_batch)
                    current_batch = []
                    current_batch_tokens = 0
        
        # Add the last batch if not empty
        if current_batch:
            batches.append(current_batch)
            
        logger.info(f"Created {len(batches)} batches from {len(all_chunks)} document chunks")
        
        # Double-check all batches fit within context window
        for i, batch in enumerate(batches):
            batch_text = "\n---\n".join(batch)
            batch_tokens = self._estimate_tokens(batch_text) + overhead_tokens
            
            if batch_tokens > self.max_input_tokens:
                logger.warning(f"Batch {i+1} exceeds context window ({batch_tokens} tokens). Reducing...")
                
                # If more than one chunk, keep only the first
                if len(batch) > 1:
                    batches[i] = [batch[0]]
                else:
                    # Otherwise truncate the single chunk
                    max_chars = (self.max_input_tokens - overhead_tokens - safety_buffer) * 3
                    batches[i] = [batch[0][:max_chars]]
        
        return batches
    
    async def _process_batch(self, batch: List[str]) -> Tuple[str, bool]:
        """
        Process a single batch of document chunks with minimal prompting
        
        Args:
            batch: List of document text chunks for this batch
            
        Returns:
            Tuple of (analysis result, success flag)
        """
        # Use minimal prompt to conserve context window space
        combined_text = "\n---\n".join(batch)
        
        prompt = f"""
        Analyze this legal document excerpt and extract:
        - Property details (location, measurements, identifiers)
        - Ownership information and transfers
        - Key dates and registration details
        
        Document:
        {combined_text}
        """
        
        # Ultra-minimal system message
        system_message = "You are a legal assistant."
        estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
        
        logger.debug(f"Estimated token usage for batch request: {estimated_tokens}")
        
        if estimated_tokens > self.max_input_tokens:
            logger.error(f"Batch exceeds context window ({estimated_tokens} > {self.max_input_tokens}).")
            
            # If the batch is too large, simplify by taking just one document
            if len(batch) > 1:
                batch = [batch[0]]
                combined_text = batch[0]
                prompt = prompt.replace("{combined_text}", combined_text)
                estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
                
                if estimated_tokens > self.max_input_tokens:
                    # If still too large, truncate
                    max_chars = (self.max_input_tokens - self._estimate_tokens(system_message) - 200) * 3
                    truncated_text = combined_text[:max_chars]
                    prompt = prompt.replace(combined_text, truncated_text)
                    estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
                    
                    logger.warning(f"Truncated batch to {estimated_tokens} tokens")
                    
                    if estimated_tokens > self.max_input_tokens:
                        return f"Error: Document too large to process within context window.", False
            else:
                return f"Error: Document too large for analysis.", False
        
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
                
                # Set a small max_tokens to leave room in the context window
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=800,  # Smaller to fit in 2048 context window
                    temperature=0.2
                )
                
                # Update token history
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                self._update_token_history(tokens_used)
                
                logger.info(f"Batch analysis completed. Tokens used: {tokens_used}")
                return response.choices[0].message.content, True
                
            except Exception as e:
                error_message = str(e)
                
                # Check for context length exceeded error
                if "context_length_exceeded" in error_message or "reduce the length" in error_message:
                    logger.error(f"Context length exceeded: {error_message}")
                    
                    if attempt == max_retries - 1:
                        # Failed after all retries
                        return f"Error: Unable to process document due to size constraints.", False
                    else:
                        # Try with smaller content
                        if len(batch) > 1:
                            # Use just the first document
                            batch = [batch[0]]
                        else:
                            # Take half of the single document
                            batch[0] = batch[0][:len(batch[0])//2]
                            
                        # Regenerate prompt
                        combined_text = "\n---\n".join(batch)
                        prompt = prompt.replace("{combined_text}", combined_text)
                
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
            # Prepare batches with proper chunking for small context window
            batches = self._prepare_batches(document_texts)
            
            if not batches:
                return "Error: Failed to prepare document batches for processing."
            
            # Process each batch in parallel for efficiency
            batch_results = []
            successful_results = []
            
            # Process batches sequentially to respect rate limits
            for i, batch in enumerate(batches):
                logger.info(f"Processing batch {i+1}/{len(batches)} with {len(batch)} chunks")
                result, success = await self._process_batch(batch)
                
                batch_results.append(result)
                if success and not result.startswith("Error"):
                    successful_results.append(result)
            
            # Check if we have any successful results
            if not successful_results:
                logger.error("No successful batch processing results")
                return "Error: Unable to process any document sections successfully. The document may be too complex for analysis."
            
            # With small context window, we need to process the combined report in stages
            if len(successful_results) == 1:
                # Only one result, so return it directly
                return self._format_final_report(successful_results[0])
            elif len(successful_results) <= 5:
                # Few enough results to combine in one step
                combined_report = await self._combine_batch_reports(successful_results)
                return self._format_final_report(combined_report)
            else:
                # Too many results, process in groups
                logger.info(f"Many batch results ({len(successful_results)}), combining in groups")
                
                # Combine in groups of 3
                group_size = 3
                grouped_results = []
                
                for i in range(0, len(successful_results), group_size):
                    group = successful_results[i:i+group_size]
                    if len(group) == 1:
                        grouped_results.append(group[0])
                    else:
                        combined = await self._combine_batch_reports(group)
                        grouped_results.append(combined)
                
                # Now combine the grouped results
                if len(grouped_results) == 1:
                    return self._format_final_report(grouped_results[0])
                else:
                    final_report = await self._combine_batch_reports(grouped_results)
                    return self._format_final_report(final_report)
                    
        except Exception as e:
            logger.error(f"Error during document analysis: {str(e)}")
            return f"Error analyzing documents: {str(e)}"
    
    def _format_final_report(self, report_content: str) -> str:
        """
        Format the final report with a standardized structure
        
        Args:
            report_content: The raw report content
            
        Returns:
            Formatted report
        """
        # Add standard title report format if not already present
        if "REPORT ON TITLE" not in report_content and "Title Report" not in report_content:
            current_date = time.strftime("%B %d, %Y")
            
            # Extract property details if possible
            property_details = "See details in report body"
            
            formatted_report = f"""
# REPORT ON TITLE
Date: {current_date}

Re: {property_details}

{report_content}

THE SCHEDULE ABOVE REFERRED TO
(See details in the report body)
            """
            return formatted_report.strip()
        
        return report_content
    
    async def _combine_batch_reports(self, batch_results: List[str]) -> str:
        """
        Combine multiple batch results into a coherent report, respecting 2048 token context window
        
        Args:
            batch_results: List of analysis results from each batch
            
        Returns:
            Combined report
        """
        logger.info(f"Combining {len(batch_results)} batch results into a single report")
        
        if len(batch_results) == 1:
            return batch_results[0]
            
        # Use a very minimal prompt for combining results to save context space
        # Instead of sending all results at once, summarize key points
        system_message = "You are a legal assistant."
        
        # Extract summaries from each result (first few lines) to reduce token usage
        summarized_results = []
        for i, result in enumerate(batch_results):
            # Get first 5 lines or 300 chars, whichever is shorter
            lines = result.split('\n')[:5]
            summary = '\n'.join(lines)
            if len(summary) > 300:
                summary = summary[:300] + "..."
            summarized_results.append(f"Section {i+1}:\n{summary}")
        
        combined_text = "\n\n---\n\n".join(summarized_results)
        
        prompt = f"""
        You have analyzed multiple sections of a legal document. Create a coherent title report by combining these findings:
        
        {combined_text}
        
        Note: These are just summaries. Focus on organizing the key information into a standard title report format.
        """
        
        estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
        
        # If still too large for context window, use even less information
        if estimated_tokens > self.max_input_tokens:
            logger.warning(f"Combined summaries still exceed context window ({estimated_tokens} tokens)")
            
            # Just use first and last result with minimal context
            first_result = batch_results[0]
            last_result = batch_results[-1]
            
            # Truncate even more aggressively
            first_summary = first_result.split('\n')[0][:200]
            last_summary = last_result.split('\n')[0][:200]
            
            prompt = f"""
            Create a title report by combining information from different document sections.
            
            First section begins with: {first_summary}...
            
            Last section begins with: {last_summary}...
            
            There were {len(batch_results)} total sections analyzed.
            """
            
            estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
            
            if estimated_tokens > self.max_input_tokens:
                logger.error(f"Cannot fit even minimal combined prompt in context window")
                return "# TITLE REPORT\n\nMultiple document sections were analyzed. Due to processing limitations, please refer to the individual section analyses."
        
        # Check rate limit
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        # Process the combination request
        max_retries = 2
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending combination request to Groq API (attempt {attempt + 1}/{max_retries})")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=800,
                    temperature=0.2
                )
                
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                self._update_token_history(tokens_used)
                
                logger.info(f"Report combination completed. Tokens used: {tokens_used}")
                return response.choices[0].message.content
                
            except Exception as e:
                error_message = str(e)
                
                if "context_length_exceeded" in error_message or "reduce the length" in error_message:
                    if attempt == max_retries - 1:
                        # Use an ultra-minimal approach as fallback
                        return "# TITLE REPORT\n\nThis report combines analysis from multiple document sections. The combined document was too large for complete analysis in one pass."
                    else:
                        # Try with much less content
                        prompt = f"""
                        Create a title report outline based on analyzing multiple document sections.
                        There were {len(batch_results)} sections total.
                        """
                elif attempt < max_retries - 1:
                    wait_time = 1
                    logger.warning(f"API call failed: {error_message}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All combination retry attempts failed: {error_message}")
                    return "# TITLE REPORT\n\nMultiple document sections were analyzed. Due to API constraints, please refer to individual section analyses."