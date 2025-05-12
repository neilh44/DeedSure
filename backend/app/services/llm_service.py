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
        You are an expert legal document specialist with deep knowledge of Indian property law, title searches, and land record documentation. Generate a comprehensive Title Search Report (TSR) based on the following property documents:

        ## Document Content:
        {combined_text}

        Follow these instructions to create your report:

        1. Create a professional header with:
           - Title "TITLE SEARCH REPORT (TSR)" 
           - Addressee (Branch Manager and financial institution)
           - Your details as legal professional with contact information

        2. Extract and document all property identifiers including:
           - Survey/Block numbers (both new and old)
           - City Survey numbers and area measurements
           - Complete location details (Village/Mouje, Taluka, District, Sub-District)
           - Property boundaries in all four directions

        3. Document the chain of title chronologically by:
           - Starting with earliest recorded owners
           - Including all mutation entries with numbers and dates
           - Documenting resurvey proceedings and resulting allocations
           - Including all Ganot Cases or special land proceedings

        4. List all examined documents with their details:
           - Original Sale/Lease Deed numbers with execution dates
           - Power of Attorney documents with precise dates
           - Indemnity Bonds and other supporting documents
           - Village forms and City Survey Property Cards

        5. Clearly state the encumbrance status and note:
           - Any existing mortgages, liens, or charges
           - Any restrictions on title or land usage
           - Outstanding claims or notices against the property

        6. Provide specific security recommendations for:
           - Protecting the financial institution's interests
           - Necessary regulatory compliance steps
           - Required tax documentation and verification

        # TITLE SEARCH REPORT (TSR)

        To: [Branch Manager Name and Financial Institution]  
        From: [Legal Professional's Name, Designation and Contact Details]

        ### 1. Document Receipt and Handover Details
        [Table format with dates and officials involved]

        ### 2. Borrower/Mortgagor Details
        [Account holder and property owner details]

        ### 3. Property Description
        3.1 Nature of property: [N.A. Land/Agricultural/Residential etc.]
        3.2 Survey/Block Numbers: [All relevant survey numbers with old/new designations]
        3.3 Boundaries and Measurement: [Complete boundary description with directions]

        ### 4. Title Tracing
        [Chronological narrative of ownership with all mutation entries, dates and legal proceedings]

        ### 5. Documents Examined
        [Numbered list of all legal documents with their registration details]

        ### 6. Encumbrance Certificate
        [Clear statement about presence or absence of encumbrances]

        ### 7. Recommendations
        [Specific suggestions to protect lender's interests]

        Date: [Current Date]
        Place: [Location]

        [Signature Block]
        Advocate/Legal Consultant
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
            max_tokens=5000,
            temperature=0.2
        )
        
        # Update token history with actual tokens used
        tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
        self._update_token_history(tokens_used)
        
        return response.choices[0].message.content