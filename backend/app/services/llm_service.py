import asyncio
from typing import Dict, Any, List, Optional, Tuple
import groq
import time
import logging
from collections import deque
import re
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with Groq LLM API with rate limiting and error handling"""
    
    def __init__(self):
        self.client = groq.Client(api_key=settings.GROQ_API_KEY)
        self.model = settings.LLM_MODEL
        
        # Rate limiting settings
        self.token_limit_per_minute = 5500
        self.token_limit_per_request = 6000
        self.token_history = deque()  # Stores (timestamp, token_count) tuples
        self.window_size_seconds = 60  # 1 minute window
        
        # LLaMA-3-8b-8192 has a context window of 2048 tokens
        self.model_context_window = 2048
        
        # Document processing settings - based on reference
        self.chunk_size = 1000  # characters (roughly 300-350 tokens)
        self.chunk_overlap = 200  # character overlap between chunks
        self.max_input_tokens = 1200  # Reserve ~800 tokens for prompt and response
        
        logger.info(f"LLMService initialized with model {self.model}, token limit {self.token_limit_per_minute}/minute, " +
                  f"{self.token_limit_per_request}/request, and context window {self.model_context_window}")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Roughly estimate the number of tokens in the text.
        Using a conservative estimate to avoid underestimation.
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
    
    def _recursive_split_text(self, text: str) -> List[str]:
        """
        Recursively split text using different separators to create logical chunks
        Based on RecursiveCharacterTextSplitter approach
        
        Args:
            text: Document text content
            
        Returns:
            List of text chunks
        """
        # Define separators in order of priority
        separators = [
            "\n\n",  # Double line break (paragraphs)
            "\n",    # Single line break
            ". ",    # End of sentence
            ", ",    # Comma clause
            " ",     # Words
            ""       # Characters
        ]
        
        # If text is already small enough, return it as a single chunk
        if len(text) <= self.chunk_size:
            return [text]
        
        # Try each separator
        for separator in separators:
            if separator == "":
                # Character-level splitting as last resort
                return [text[i:i+self.chunk_size] for i in range(0, len(text), self.chunk_size-self.chunk_overlap)]
            
            # Split on this separator
            if separator in text:
                splits = text.split(separator)
                
                # If splitting results in pieces that are too large, continue to next separator
                if max(len(s) for s in splits) > self.chunk_size:
                    continue
                
                # Recombine splits to form chunks of approximately the desired size
                chunks = []
                current_chunk = []
                current_length = 0
                
                for split in splits:
                    split_with_sep = split if separator == "" else split + separator
                    split_length = len(split_with_sep)
                    
                    # If this split would make the chunk too big, start a new chunk
                    if current_length + split_length > self.chunk_size and current_chunk:
                        chunks.append(separator.join(current_chunk))
                        
                        # For overlap, include the last piece(s) from the previous chunk
                        overlap_length = 0
                        overlap_pieces = []
                        
                        for piece in reversed(current_chunk):
                            piece_length = len(piece) + len(separator)
                            if overlap_length + piece_length <= self.chunk_overlap:
                                overlap_pieces.insert(0, piece)
                                overlap_length += piece_length
                            else:
                                break
                                
                        current_chunk = overlap_pieces
                        current_length = overlap_length
                    
                    current_chunk.append(split)
                    current_length += split_length
                
                # Add the last chunk if not empty
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                
                return chunks
        
        # If we get here, no separator worked well - just use character-level splitting
        return [text[i:i+self.chunk_size] for i in range(0, len(text), self.chunk_size-self.chunk_overlap)]
    
    def _split_documents(self, document_texts: List[str]) -> List[Dict[str, Any]]:
        """
        Split documents into overlapping chunks using recursive text splitter
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            List of chunks with metadata
        """
        all_chunks = []
        
        for doc_idx, doc_text in enumerate(document_texts):
            # Add document metadata to help with context
            doc_metadata = {
                "document_index": doc_idx,
                "total_documents": len(document_texts),
                "document_length": len(doc_text),
                "document_preview": doc_text[:100].replace('\n', ' ').strip() + "..."
            }
            
            # Split document using recursive text splitter
            chunks = self._recursive_split_text(doc_text)
            logger.info(f"Document {doc_idx+1} split into {len(chunks)} chunks")
            
            # Add metadata to each chunk
            for i, chunk_text in enumerate(chunks):
                all_chunks.append({
                    "content": chunk_text,
                    "chunk_index": i,
                    "total_chunks": len(chunks),
                    "tokens": self._estimate_tokens(chunk_text),
                    "document_index": doc_idx,
                    "is_first_chunk": i == 0,
                    "is_last_chunk": i == len(chunks) - 1,
                    "metadata": doc_metadata
                })
        
        logger.info(f"Created {len(all_chunks)} total chunks from {len(document_texts)} documents")
        return all_chunks
    
    def _prepare_batches(self, document_texts: List[str]) -> List[Dict[str, Any]]:
        """
        Process documents and create batches for processing
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            List of batch objects with processing information
        """
        # Split documents into overlapping chunks
        chunks = self._split_documents(document_texts)
        
        # Create a batch for each chunk
        batches = []
        
        for chunk in chunks:
            # Create prompt for this chunk
            prompt = self._create_prompt_for_chunk(chunk)
            system_message = "You are a specialized legal assistant with expertise in property law and title searches."
            
            # Calculate estimated tokens
            overhead_tokens = self._estimate_tokens(system_message) + self._estimate_tokens(prompt) - chunk["tokens"]
            estimated_tokens = overhead_tokens + chunk["tokens"]
            
            # Ensure it fits within limits
            if estimated_tokens > self.max_input_tokens:
                logger.warning(f"Chunk {chunk['chunk_index']} exceeds token limits. Truncating.")
                # Calculate maximum content size
                max_content_tokens = self.max_input_tokens - overhead_tokens - 50
                max_content_chars = max_content_tokens * 3
                
                if len(chunk["content"]) > max_content_chars:
                    chunk["content"] = chunk["content"][:max_content_chars]
                    chunk["tokens"] = self._estimate_tokens(chunk["content"])
                    chunk["truncated"] = True
                    
                    # Recalculate with truncated content
                    prompt = self._create_prompt_for_chunk(chunk)
                    estimated_tokens = overhead_tokens + chunk["tokens"]
            
            batches.append({
                "chunk": chunk,
                "prompt": prompt,
                "system_message": system_message,
                "estimated_tokens": estimated_tokens
            })
        
        return batches
    
    def _create_prompt_for_chunk(self, chunk: Dict[str, Any]) -> str:
        """
        Create an appropriate prompt for a specific chunk
        
        Args:
            chunk: Document chunk with metadata
            
        Returns:
            Prompt for this chunk
        """
        # Get chunk position context
        position = ""
        if chunk["is_first_chunk"]:
            position = "This is the beginning of the document."
        elif chunk["is_last_chunk"]:
            position = "This is the end of the document."
        else:
            position = f"This is part {chunk['chunk_index']+1} of {chunk['total_chunks']} from the document."
        
        # Create prompt with context
        prompt = f"""
        Analyze this portion of a legal document to extract relevant information for a title report.
        
        {position}
        Document preview: {chunk['metadata']['document_preview']}
        
        Content to analyze:
        {chunk['content']}
        
        Extract all property-related information from this section, including:
        1. Property details (Survey/Plot numbers, measurements, location)
        2. Party information (names, roles)
        3. Transaction details with exact dates
        4. Registration details (numbers, dates, offices)
        5. Encumbrances or restrictions
        6. Boundary information
        
        Format your response as a clear section that can be combined with analysis of other document parts.
        """
        
        return prompt
    
    async def _process_batch(self, batch: Dict[str, Any]) -> Tuple[str, Dict[str, Any], bool]:
        """
        Process a single batch
        
        Args:
            batch: Batch object with chunk and processing info
            
        Returns:
            Tuple of (analysis result, metadata, success flag)
        """
        chunk = batch["chunk"]
        prompt = batch["prompt"]
        system_message = batch["system_message"]
        estimated_tokens = batch["estimated_tokens"]
        
        logger.debug(f"Processing chunk {chunk['chunk_index']+1}/{chunk['total_chunks']} from document {chunk['document_index']+1}")
        
        # Check rate limit
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        # Process with retries
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending chunk {chunk['chunk_index']+1} to Groq API (attempt {attempt+1}/{max_retries})")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=800,
                    temperature=0.2
                )
                
                # Update token usage
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                self._update_token_history(tokens_used)
                
                logger.info(f"Chunk processed successfully. Tokens used: {tokens_used}")
                
                # Add chunk metadata to help with combining results
                result_metadata = {
                    "chunk_index": chunk["chunk_index"],
                    "total_chunks": chunk["total_chunks"],
                    "document_index": chunk["document_index"],
                    "tokens_used": tokens_used,
                    "is_first_chunk": chunk["is_first_chunk"],
                    "is_last_chunk": chunk["is_last_chunk"]
                }
                
                return response.choices[0].message.content, result_metadata, True
                
            except Exception as e:
                error_message = str(e)
                
                if "context_length_exceeded" in error_message or "reduce the length" in error_message:
                    logger.error(f"Context length exceeded: {error_message}")
                    
                    if attempt == max_retries - 1:
                        return f"Error: Unable to process this section due to size constraints.", chunk, False
                    else:
                        # Simplify prompt for next attempt
                        prompt = f"""
                        Extract property-related information from this legal document section:
                        
                        {chunk['content'][:800]}...
                        
                        Focus on property details, parties, dates, and registrations.
                        """
                        system_message = "You are a legal assistant."
                
                elif attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"API call failed: {error_message}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed: {error_message}")
                    return f"Error processing document section: {error_message}", chunk, False
    
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
            # Prepare batches with overlapping chunks
            batches = self._prepare_batches(document_texts)
            
            if not batches:
                return "Error: Failed to prepare document batches for processing."
            
            # Process each batch
            results = []
            metadata_list = []
            
            for i, batch in enumerate(batches):
                logger.info(f"Processing batch {i+1}/{len(batches)}")
                result, metadata, success = await self._process_batch(batch)
                
                # Add section header to help with report organization
                if success:
                    section_marker = f"### Document {metadata['document_index']+1} - Section {metadata['chunk_index']+1}\n\n"
                    results.append(section_marker + result)
                    metadata_list.append(metadata)
                else:
                    # Include error message
                    section_marker = f"### Document {batch['chunk']['document_index']+1} - Section {batch['chunk']['chunk_index']+1} (Error)\n\n"
                    results.append(section_marker + result)
            
            # Generate the final report
            combined_report = await self._generate_final_report(results, metadata_list, document_texts)
            return combined_report
                
        except Exception as e:
            logger.error(f"Error during document analysis: {str(e)}")
            return f"Error analyzing documents: {str(e)}"
    
    async def _extract_structured_information(self, chunk_results: List[str]) -> Dict[str, str]:
        """
        Extract structured information from chunk analysis results
        
        Args:
            chunk_results: List of analysis results from each chunk
            
        Returns:
            Dictionary of structured information categories
        """
        # Use a small portion of the results to fit context window
        combined_text = "\n\n".join(chunk_results[:15])  # Limit to fit context
        
        prompt = f"""
        Extract structured information from these document analyses for a title report:
        
        {combined_text[:3000]}
        
        Extract and summarize ONLY the following key categories:
        
        PROPERTY_DETAILS: [Property identifiers, measurements and location]
        
        OWNERSHIP: [All owners and transfers with dates]
        
        REGISTRATION: [Registration numbers, dates and offices]
        
        ENCUMBRANCES: [Any claims, mortgages or restrictions]
        
        BOUNDARIES: [Property boundaries]
        
        SCHEDULE: [The property schedule description]
        """
        
        system_message = "You are a legal assistant extracting key information for a title report."
        
        # Check rate limit
        estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        try:
            logger.info("Extracting structured information from chunk results")
            
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
            
            # Parse the response into structured categories
            result = response.choices[0].message.content
            structured_info = {}
            
            # Extract each category using regex
            for category in ["PROPERTY_DETAILS", "OWNERSHIP", "REGISTRATION", "ENCUMBRANCES", "BOUNDARIES", "SCHEDULE"]:
                pattern = f"{category}:\\s*(.*?)(?=\\n\\n[A-Z_]+:|$)"
                match = re.search(pattern, result, re.DOTALL)
                if match:
                    structured_info[category.lower()] = match.group(1).strip()
                else:
                    structured_info[category.lower()] = f"No {category.lower()} information identified."
            
            return structured_info
            
        except Exception as e:
            logger.error(f"Error extracting structured information: {str(e)}")
            return {
                'property_details': "Please review the document analyses for property details.",
                'ownership': "Please review the document analyses for ownership information.",
                'registration': "Please review the document analyses for registration details.",
                'encumbrances': "Please review the document analyses for encumbrance information.",
                'boundaries': "Please review the document analyses for boundary information.",
                'schedule': "Please review the document analyses for schedule information."
            }
    
    async def _generate_final_report(self, chunk_results: List[str], 
                               chunk_metadata: List[Dict[str, Any]],
                               document_texts: List[str]) -> str:
        """
        Generate the final title report from all chunk results
        
        Args:
            chunk_results: List of analysis results from each chunk
            chunk_metadata: List of metadata for each chunk
            document_texts: Original document texts
            
        Returns:
            Final title report
        """
        logger.info(f"Generating final report from {len(chunk_results)} chunk results")
        
        # Extract structured information categories
        structured_info = await self._extract_structured_information(chunk_results)
        
        # Generate formatted report
        current_date = time.strftime("%B %d, %Y")
        
        report = f"""
# REPORT ON TITLE
Date: {current_date}

## PROPERTY DETAILS
{structured_info.get('property_details', 'Property details could not be determined from the provided documents.')}

## OWNERSHIP AND CHAIN OF TITLE
{structured_info.get('ownership', 'Ownership information could not be determined from the provided documents.')}

## REGISTRATION DETAILS
{structured_info.get('registration', 'Registration details could not be determined from the provided documents.')}

## ENCUMBRANCES
{structured_info.get('encumbrances', 'No encumbrances were identified in the provided documents.')}

## BOUNDARIES
{structured_info.get('boundaries', 'Property boundaries could not be determined from the provided documents.')}

## THE SCHEDULE ABOVE REFERRED TO
{structured_info.get('schedule', 'Schedule details could not be determined from the provided documents.')}

---

This report was generated based on {len(document_texts)} document(s) processed in {len(chunk_results)} sections.
For a comprehensive title search, please consult with a legal professional.
"""
        
        # Clean up the report
        report = re.sub(r'\n{3,}', '\n\n', report)
        
        return report.strip()