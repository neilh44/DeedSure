import asyncio
from typing import Dict, Any, List, Optional
import groq
import time
import logging
from collections import deque

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with Groq LLM API with rate limiting and error handling"""
    
    def __init__(self, api_key: str, model: str = "llama3-70b-8192"):
        self.client = groq.Client(api_key=api_key)
        self.model = model
        
        # Rate limiting settings
        self.token_limit_per_minute = 50000
        self.token_history = deque()  # Stores (timestamp, token_count) tuples
        self.window_size_seconds = 60  # 1 minute window
        
        logger.info(f"LLMService initialized with model {self.model}")
    
    def _estimate_tokens(self, text: str) -> int:
        """Roughly estimate the number of tokens in the text."""
        return len(text) // 4
    
    def _update_token_history(self, tokens_used: int) -> None:
        """Add tokens to history and remove entries older than window size"""
        current_time = time.time()
        self.token_history.append((current_time, tokens_used))
        
        # Remove entries older than our window
        while self.token_history and self.token_history[0][0] < current_time - self.window_size_seconds:
            self.token_history.popleft()
    
    def _get_current_token_usage(self) -> int:
        """Calculate total tokens used in the current time window"""
        return sum(tokens for _, tokens in self.token_history)
    
    def _check_rate_limit(self, estimated_tokens: int) -> float:
        """Check if sending this many tokens would exceed rate limit
        Returns wait time in seconds, or 0 if no wait needed"""
        current_usage = self._get_current_token_usage()
        
        if current_usage + estimated_tokens <= self.token_limit_per_minute:
            return 0
        
        # Calculate how long to wait
        if not self.token_history:
            return 0
            
        oldest_timestamp = self.token_history[0][0]
        time_to_wait = (oldest_timestamp + self.window_size_seconds) - time.time()
        return max(0, time_to_wait)
    
    async def analyze_documents(self, document_texts: List[str]) -> str:
        """Send documents to LLM for comprehensive title chain analysis
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            Structured title report text with complete chain of title
        """
        if not document_texts:
            logger.warning("No document texts provided for analysis")
            return "Error: No documents provided for analysis."
            
        logger.info(f"Analyzing {len(document_texts)} documents with LLM")
        
        try:
            combined_text = "\n\n---DOCUMENT SEPARATOR---\n\n".join(document_texts)
            
            prompt = f"""
            You are a specialized legal assistant with expertise in property law and title searches. 
            Analyze the following property documents to generate a COMPREHENSIVE CHAIN OF TITLE with EVERY transfer and transaction in chronological order.

            ## KEY INSTRUCTIONS:
            1. EXTRACT EVERY TRANSACTION & ENTRY in the document history
            2. Begin with the EARLIEST recorded owner and proceed chronologically to present
            3. For EACH entry in the chain, include:
               - Entry/registration number
               - Exact date (DD/MM/YYYY format)
               - Complete names of ALL parties (transferors and transferees)
               - Type of transaction (sale, inheritance, subdivision, land use change, etc.)
               - Survey/block numbers with precise measurements

            4. PAY SPECIAL ATTENTION to:
               - Mutation records (numbered entries)
               - Non-agricultural conversion orders
               - Changes in survey numbers or subdivision of plots
               - Court orders or government notifications

            5. IDENTIFY ANY GAPS in the title chain

            ## Document Content:
            {combined_text}

            ## FORMAT:
            
            # COMPLETE CHAIN OF TITLE REPORT
            
            PROPERTY IDENTIFICATION:
            - UPIN/ID: [Property ID]
            - Survey/Block Number: [Number]
            - Location: [Village/Taluka/District]
            - Area: [Measurement with units]
            - Current Classification: [Type]
            
            CHAIN OF TITLE (CHRONOLOGICAL):
            
            1. [EARLIEST ENTRY]
               Date: [DD/MM/YYYY]
               Entry No.: [Number if available]
               Transaction: [Type]
               Parties: [All parties]
               Survey No.: [Number]
               Area: [Measurement]
               Details: [Description]
            
            [CONTINUE FOR EACH TRANSACTION]
            
            CURRENT OWNERSHIP:
            Based on the chain of title, the current legal owner(s) is/are [Names] as evidenced by [latest transaction details].
            """
            
            # Estimate tokens for this request
            system_message = "You are a property law expert specializing in title analysis."
            estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
            
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
                    
                    # Update token history with actual tokens used
                    tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                    self._update_token_history(tokens_used)
                    
                    logger.info(f"LLM analysis completed. Tokens used: {tokens_used}")
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