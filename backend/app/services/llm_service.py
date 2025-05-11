from typing import Dict, Any, List, Optional
import groq
import time
from collections import deque
from app.core.config import settings

class LLMService:
    """Service for interacting with Groq LLM API with rate limiting"""
    
    def __init__(self):
        self.client = groq.Client(api_key=settings.GROQ_API_KEY)
        self.model = settings.LLM_MODEL
        
        # Rate limiting settings
        self.token_limit_per_minute = 5500
        self.token_history = deque()  # Stores (timestamp, token_count) tuples
        self.window_size_seconds = 60  # 1 minute window
    
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
        return max(0, time_to_wait)
    
    async def analyze_documents(self, document_texts: List[str]) -> str:
        """
        Send documents to LLM for title report generation with rate limiting
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            Structured title report text
        """
        combined_text = "\n\n---DOCUMENT SEPARATOR---\n\n".join(document_texts)
        
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
        
        # Check rate limit
        wait_time = self._check_rate_limit(estimated_tokens)
        if wait_time > 0:
            # Wait until we can process this request
            time.sleep(wait_time)
        
        # Call Groq API
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
        
        return response.choices[0].message.content