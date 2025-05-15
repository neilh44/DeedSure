import asyncio
from typing import Dict, Any, List, Optional, Tuple
import groq
import time
import logging
from collections import deque
import re
from datetime import datetime
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
        
        # Document processing settings
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
    
    def _identify_document_sections(self, text: str) -> List[Dict[str, Any]]:
        """
        Identify logical sections in the document
        
        Args:
            text: Document text content
            
        Returns:
            List of sections with title and content
        """
        # Key section patterns for property documents
        section_patterns = [
            # Common section headers in property documents
            r'(?i)(TITLE DEED|SALE DEED|CONVEYANCE DEED|LEASE DEED)',
            r'(?i)(SCHEDULE OF PROPERTY|DESCRIPTION OF PROPERTY|THE SCHEDULE ABOVE REFERRED)',
            r'(?i)(WITNESSETH|NOW THIS DEED|NOW THEREFORE)',
            r'(?i)(WHEREAS|RECITALS|PREAMBLE)',
            r'(?i)(BOUNDARIES|BOUNDED AS FOLLOWS)',
            r'(?i)(TERMS AND CONDITIONS|COVENANTS)',
            r'(?i)(IN WITNESS WHEREOF|SIGNED AND DELIVERED)',
            r'(?i)(REGISTRATION DETAILS|REGISTRATION CERTIFICATE)',
            r'(?i)(SURVEY DETAILS|SURVEY CERTIFICATE)',
            r'(?i)(CHAIN OF TITLE|TITLE HISTORY)',
            # Numbered sections and articles
            r'(?i)(ARTICLE|CLAUSE|SECTION)\s+[IVXLCDM\d]+',
            r'(?i)(\d+\.|\([a-z]\)|\([ivx]+\))'
        ]
        
        # Identify potential section breaks
        section_breaks = [0]  # Start of document
        
        # Find matches for section patterns
        for pattern in section_patterns:
            for match in re.finditer(pattern, text):
                # Find the start of the line containing the match
                line_start = text.rfind('\n', 0, match.start()) + 1
                if line_start > 0:
                    section_breaks.append(line_start)
                else:
                    section_breaks.append(match.start())
        
        # Also look for lines that are all uppercase (potential section headers)
        lines = text.split('\n')
        offset = 0
        for line in lines:
            stripped = line.strip()
            # Check if line is mostly uppercase and at least 5 chars
            if stripped and len(stripped) >= 5 and sum(1 for c in stripped if c.isupper()) / len(stripped) > 0.7:
                section_breaks.append(offset)
            offset += len(line) + 1  # +1 for newline
        
        # Add end of document
        section_breaks.append(len(text))
        
        # Sort and deduplicate section breaks
        section_breaks = sorted(set(section_breaks))
        
        # Create sections
        sections = []
        for i in range(len(section_breaks) - 1):
            start = section_breaks[i]
            end = section_breaks[i + 1]
            
            # Get section content
            section_content = text[start:end].strip()
            if not section_content:
                continue
                
            # Get the first line as section title
            lines = section_content.split('\n', 1)
            title = lines[0].strip()
            content = section_content
            
            sections.append({
                "title": title,
                "content": content,
                "start": start,
                "end": end
            })
        
        # If no sections found, just split by paragraphs
        if len(sections) <= 1:
            paragraphs = re.split(r'\n\s*\n', text)
            sections = []
            
            start = 0
            for para in paragraphs:
                if not para.strip():
                    continue
                
                end = start + len(para)
                
                # Use first line or first few words as title
                lines = para.split('\n', 1)
                title = lines[0].strip()
                if len(title) > 40:
                    title = title[:40] + "..."
                
                sections.append({
                    "title": title,
                    "content": para.strip(),
                    "start": start,
                    "end": end
                })
                
                start = end + 2  # +2 for paragraph separator
        
        logger.info(f"Identified {len(sections)} logical sections in document")
        return sections
    
    def _create_chunks(self, sections: List[Dict[str, Any]], text: str) -> List[Dict[str, Any]]:
        """
        Create overlapping chunks from document sections
        
        Args:
            sections: List of document sections
            text: Full document text
            
        Returns:
            List of chunks with metadata
        """
        chunks = []
        
        # For very small documents, just use one chunk
        if len(text) < self.chunk_size:
            chunks.append({
                "title": "Full Document",
                "content": text,
                "sections": [s["title"] for s in sections],
                "tokens": self._estimate_tokens(text)
            })
            return chunks
            
        # First pass: try to keep sections together if possible
        for section in sections:
            section_text = section["content"]
            section_tokens = self._estimate_tokens(section_text)
            
            # If section fits in a chunk, keep it whole
            if section_tokens <= self.max_input_tokens * 0.8:  # 80% of max to leave room for prompt
                chunks.append({
                    "title": section["title"],
                    "content": section_text,
                    "sections": [section["title"]],
                    "tokens": section_tokens
                })
            else:
                # Split large section into smaller chunks
                chunk_texts = []
                
                # Try to split by paragraphs first
                paragraphs = re.split(r'\n\s*\n', section_text)
                
                if len(paragraphs) > 1:
                    # Process paragraphs
                    current_chunk = []
                    current_tokens = 0
                    
                    for para in paragraphs:
                        para_tokens = self._estimate_tokens(para)
                        
                        # If adding this paragraph would exceed chunk size
                        if current_tokens + para_tokens > self.chunk_size and current_chunk:
                            # Add current chunk
                            chunk_texts.append("\n\n".join(current_chunk))
                            
                            # Start new chunk with overlap
                            overlap_content = current_chunk[-1] if current_chunk else ""
                            current_chunk = [overlap_content, para] if overlap_content else [para]
                            current_tokens = self._estimate_tokens("\n\n".join(current_chunk))
                        else:
                            current_chunk.append(para)
                            current_tokens += para_tokens
                    
                    # Add the last chunk
                    if current_chunk:
                        chunk_texts.append("\n\n".join(current_chunk))
                else:
                    # If no paragraphs, split by sentences
                    sentences = re.split(r'(?<=[.!?])\s+', section_text)
                    
                    current_chunk = []
                    current_tokens = 0
                    
                    for sentence in sentences:
                        sentence_tokens = self._estimate_tokens(sentence)
                        
                        if current_tokens + sentence_tokens > self.chunk_size and current_chunk:
                            # Add current chunk
                            chunk_texts.append(" ".join(current_chunk))
                            
                            # Start new chunk with overlap
                            overlap_content = current_chunk[-1] if current_chunk else ""
                            current_chunk = [overlap_content, sentence] if overlap_content else [sentence]
                            current_tokens = self._estimate_tokens(" ".join(current_chunk))
                        else:
                            current_chunk.append(sentence)
                            current_tokens += sentence_tokens
                    
                    # Add the last chunk
                    if current_chunk:
                        chunk_texts.append(" ".join(current_chunk))
                
                # Create chunks from the section parts
                for i, chunk_text in enumerate(chunk_texts):
                    chunks.append({
                        "title": f"{section['title']} (Part {i+1}/{len(chunk_texts)})",
                        "content": chunk_text,
                        "sections": [section["title"]],
                        "tokens": self._estimate_tokens(chunk_text)
                    })
        
        logger.info(f"Created {len(chunks)} chunks from document sections")
        return chunks
    
    def _prepare_batches(self, document_texts: List[str]) -> List[Dict[str, Any]]:
        """
        Process documents and create batches for processing
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            List of batch objects with processing information
        """
        all_chunks = []
        
        for doc_idx, doc_text in enumerate(document_texts):
            # Get document metadata
            doc_metadata = {
                "document_index": doc_idx,
                "document_length": len(doc_text)
            }
            
            # Identify document sections
            sections = self._identify_document_sections(doc_text)
            
            # Create chunks from sections
            chunks = self._create_chunks(sections, doc_text)
            
            # Add document metadata to chunks
            for chunk in chunks:
                chunk["document_index"] = doc_idx
                chunk["document_metadata"] = doc_metadata
            
            all_chunks.extend(chunks)
        
        # Create a batch for each chunk
        batches = []
        
        for chunk_idx, chunk in enumerate(all_chunks):
            # Create prompts optimized for extracting title report information
            prompt = self._create_title_report_prompt(chunk, chunk_idx, len(all_chunks))
            system_message = "You are a specialized legal assistant with expertise in property law and title searches in India."
            
            # Estimate tokens
            estimated_tokens = chunk["tokens"] + self._estimate_tokens(prompt) + self._estimate_tokens(system_message) - chunk["tokens"]
            
            batches.append({
                "chunk": chunk,
                "prompt": prompt,
                "system_message": system_message,
                "estimated_tokens": estimated_tokens,
                "chunk_index": chunk_idx,
                "total_chunks": len(all_chunks)
            })
        
        logger.info(f"Prepared {len(batches)} batches for processing")
        return batches
    
    def _create_title_report_prompt(self, chunk: Dict[str, Any], chunk_index: int, total_chunks: int) -> str:
        """
        Create a prompt specifically designed to extract title report information
        
        Args:
            chunk: Document chunk with metadata
            chunk_index: Index of this chunk
            total_chunks: Total number of chunks
            
        Returns:
            Prompt for title report extraction
        """
        # Determine chunk context
        context = f"This is chunk {chunk_index+1} of {total_chunks} from document {chunk['document_index']+1}."
        
        # Create prompt focused on title report elements
        prompt = f"""
        Analyze this portion of a legal property document to extract information for a comprehensive title report:

        {context}
        Document section: {chunk['title']}
        
        DOCUMENT CONTENT:
        {chunk['content']}
        
        Extract ALL of the following information EXACTLY AS IT APPEARS in the document (if present):
        
        1. PROPERTY DETAILS:
           - Survey/Block/Plot numbers with exact identifiers
           - Property measurements with exact figures
           - Precise location details (village, city, district)
           
        2. OWNERSHIP HISTORY:
           - Names of all parties in the chain of title
           - Exact dates of all transfers and registrations
           - Registration details with serial numbers
           
        3. ENCUMBRANCES:
           - Any claims, mortgages, or restrictions on the property
           - Details of any public notices
           
        4. BOUNDARIES:
           - Properties/landmarks on all sides (North, South, East, West)
           
        5. SCHEDULE DESCRIPTION:
           - The formal schedule of property description
        
        Format your response with clear section headings and PRESERVE ALL NUMBERS, DATES, AND NAMES EXACTLY as they appear in the document. If any information is not present in this section, indicate "Not found in this section".
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
        
        logger.debug(f"Processing chunk {batch['chunk_index']+1}/{batch['total_chunks']}")
        
        # Check rate limit
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            await asyncio.sleep(wait_time)
        
        # Process with retries
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending chunk {batch['chunk_index']+1} to Groq API (attempt {attempt+1}/{max_retries})")
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=800,
                    temperature=0.1  # Lower temperature for more factual responses
                )
                
                # Update token usage
                tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                self._update_token_history(tokens_used)
                
                logger.info(f"Chunk processed successfully. Tokens used: {tokens_used}")
                
                # Format result with section title
                result = response.choices[0].message.content
                
                result_metadata = {
                    "chunk_index": batch["chunk_index"],
                    "total_chunks": batch["total_chunks"],
                    "document_index": chunk["document_index"],
                    "tokens_used": tokens_used,
                    "section_title": chunk["title"]
                }
                
                return result, result_metadata, True
                
            except Exception as e:
                error_message = str(e)
                
                if "context_length_exceeded" in error_message or "reduce the length" in error_message:
                    logger.error(f"Context length exceeded: {error_message}")
                    
                    if attempt == max_retries - 1:
                        return f"Error: Unable to process this section due to size constraints.", {"chunk_index": batch["chunk_index"]}, False
                    else:
                        # Simplify prompt for next attempt
                        prompt = f"""
                        Analyze this legal document section and extract any property details, ownership information, and dates:
                        
                        {chunk['content'][:800]}...
                        """
                        system_message = "You are a legal assistant."
                
                elif attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.warning(f"API call failed: {error_message}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retry attempts failed: {error_message}")
                    return f"Error processing document section: {error_message}", {"chunk_index": batch["chunk_index"]}, False
    
    async def _extract_title_report_elements(self, chunk_results: List[str]) -> Dict[str, str]:
        """
        Extract structured title report elements from chunk results
        
        Args:
            chunk_results: List of analysis results from each chunk
            
        Returns:
            Dictionary of title report elements
        """
        # Combine chunk results
        combined_text = "\n\n".join(chunk_results)
        
        # Define regex patterns to extract key elements
        patterns = {
            "property_location": r'(?i)(?:located|situated)(?:\s+at|\s+in)?\s+([^\.]+)',
            "survey_numbers": r'(?i)(?:Survey|S\.\s*No\.|Plot|Block)\s*(?:No\.)?\s*[:#]?\s*([A-Za-z0-9\-\/,\s]+)',
            "property_size": r'(?i)(?:admeasuring|measuring|area|size)(?:\s+of)?\s+([0-9,\.]+\s*(?:square)?\s*(?:mts|meters|sq\.m|sq\.ft|acres|hectares|bigha|gunta))',
            "original_owner": r'(?i)(?:originally\s+owned|first\s+owned|initial\s+owner)(?:\s+by)?\s+([^\.]+)',
            "boundaries": r'(?i)(?:on\s+(?:the|or)?\s+(?:towards\s+(?:the)?)?\s+(north|south|east|west)\s*[:\.]\s*([^\.]+))',
            "registration_details": r'(?i)(?:registration|registered|registry)(?:\s+on|\s+dated|\s+date|\s+details)?\s+([^\.]+)',
            "dates": r'(?i)(?:dated|date)?\s+(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}|\d{1,2}[-\/]\d{1,2}[-\/]\d{2,4})'
        }
        
        # Extract elements
        extracted = {}
        
        for key, pattern in patterns.items():
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            if matches:
                if key == "boundaries":
                    # Special handling for boundaries
                    boundaries = {}
                    for direction, boundary in matches:
                        boundaries[direction.lower()] = boundary.strip()
                    extracted[key] = boundaries
                else:
                    # Remove duplicates while preserving order
                    unique_matches = []
                    for match in matches:
                        if isinstance(match, str) and match.strip() not in unique_matches:
                            unique_matches.append(match.strip())
                    extracted[key] = unique_matches
        
        # Use more targeted prompt to extract chain of title
        chain_prompt = f"""
        Extract the chronological chain of title from these document analyses.
        For each transfer, include:
        1. The exact date
        2. Names of transferor and transferee
        3. Any registration numbers
        
        Present as numbered points in chronological order:
        
        {combined_text[:3500]}
        """
        
        system_message = "You are a legal assistant specializing in property title searches."
        
        try:
            chain_response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": chain_prompt}
                ],
                max_tokens=800,
                temperature=0.1
            )
            
            tokens_used = chain_response.usage.prompt_tokens + chain_response.usage.completion_tokens
            self._update_token_history(tokens_used)
            
            extracted["chain_of_title"] = chain_response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error extracting chain of title: {str(e)}")
            extracted["chain_of_title"] = "Could not determine chain of title from the provided documents."
        
        return extracted
    
    async def _generate_title_report(self, elements: Dict[str, Any]) -> str:
        """
        Generate a properly formatted title report
        
        Args:
            elements: Dictionary of extracted title report elements
            
        Returns:
            Formatted title report
        """
        # Format current date
        current_date = datetime.now().strftime("%d/%m/%Y")
        
        # Prepare property description
        property_desc = ""
        if "survey_numbers" in elements and elements["survey_numbers"]:
            property_desc += f"Survey/Plot No. {elements['survey_numbers'][0]} "
            
        if "property_size" in elements and elements["property_size"]:
            property_desc += f"admeasuring {elements['property_size'][0]} "
            
        if "property_location" in elements and elements["property_location"]:
            property_desc += f"located at {elements['property_location'][0]}"
        
        if not property_desc:
            property_desc = "Property details could not be fully determined from the provided documents."
        
        # Prepare chain of title
        chain_of_title = elements.get("chain_of_title", "Chain of title could not be determined from the provided documents.")
        
        # Prepare boundaries
        boundaries = elements.get("boundaries", {})
        boundary_text = ""
        
        for direction in ["east", "west", "north", "south"]:
            if direction in boundaries:
                boundary_text += f"On or towards the {direction.capitalize()}: {boundaries[direction]}\n"
        
        if not boundary_text:
            boundary_text = "Property boundaries could not be determined from the provided documents."
        
        # Prepare report
        report = f"""
# REPORT ON TITLE
Date: {current_date}

Re.: {property_desc}

That we have caused necessary searches to be taken with the available Revenue records and Sub-Registry Records for a period of last more than Thirty Years and on perusal and verification of documents of title deeds produced to us, we give our report on title in respect of said land as under:

{chain_of_title}

THE SCHEDULE ABOVE REFERRED TO

ALL THAT piece and parcel of property {property_desc}.

{boundary_text}

[Note: This report is based on the documents provided for analysis. Additional documents may be required for a complete title search.]

[Signature Block]
        """
        
        # Clean up the report
        report = re.sub(r'\n{3,}', '\n\n', report)
        
        return report.strip()
    
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
            # Prepare batches with semantic chunking
            batches = self._prepare_batches(document_texts)
            
            if not batches:
                return "Error: Failed to prepare document batches for processing."
            
            # Process each batch
            chunk_results = []
            
            for i, batch in enumerate(batches):
                logger.info(f"Processing batch {i+1}/{len(batches)}")
                result, metadata, success = await self._process_batch(batch)
                
                if success:
                    # Add section markers to help with information extraction
                    section_result = f"# {metadata['section_title']}\n\n{result}"
                    chunk_results.append(section_result)
            
            if not chunk_results:
                return "Error: Unable to process any document sections successfully."
            
            # Extract title report elements from chunk results
            elements = await self._extract_title_report_elements(chunk_results)
            
            # Generate final formatted title report
            title_report = await self._generate_title_report(elements)
            
            return title_report
                
        except Exception as e:
            logger.error(f"Error during document analysis: {str(e)}")
            return f"Error analyzing documents: {str(e)}"