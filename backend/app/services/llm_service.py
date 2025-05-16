import asyncio
from typing import Dict, Any, List, Optional
import openai
import time
import logging
from collections import deque
import os

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with OpenAI API with rate limiting and error handling"""
    
    def __init__(self):
        # Get OpenAI API key from environment variables
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable must be set")
            
        self.client = openai.OpenAI(api_key=openai_api_key)
        self.model = os.environ.get("LLM_MODEL", "gpt-4.1")  # Default to GPT-4o if not specified
        
        # Rate limiting settings
        self.token_limit_per_minute = 40000
        self.token_history = deque()  # Stores (timestamp, token_count) tuples
        self.window_size_seconds = 60  # 1 minute window
        
        logger.info(f"LLMService initialized with model {self.model} and token limit {self.token_limit_per_minute}/minute")
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Roughly estimate the number of tokens in the text.
        For OpenAI models, ~4 chars ≈ 1 token, but this is a simple approximation.
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
    
    async def analyze_documents(self, document_texts: List[str]) -> str:
        """
        Send documents to OpenAI for title report generation with rate limiting
        
        Args:
            document_texts: List of document text contents
            
        Returns:
            Structured title report text
        """
        if not document_texts:
            logger.warning("No document texts provided for analysis")
            return "Error: No documents provided for analysis."
            
        logger.info(f"Analyzing {len(document_texts)} documents with OpenAI")
        
        try:
            combined_text = "\n\n---DOCUMENT SEPARATOR---\n\n".join(document_texts)
            
            prompt = f"""
            You are an expert legal document summarizer with deep knowledge of Indian land records and property law. 
            Prepare title clear report. Given the following land record or mutation register, extract and present the complete CHAIN OF TITLE in a structured format.

            ## KEY INSTRUCTIONS:
            Extract and organize ALL ownership transfers and significant events affecting the property in CHRONOLOGICAL ORDER (oldest to newest).

            For each entry in the chain of title, identify and include:
            1. Entry/Memo Number (નોધ નંબર)
            2. Entry Date (નોધની તારીખ) - format as DD/MM/YYYY
            3. Type of Change (ફેરફારનો પ્રકાર) - e.g., sale, inheritance, conversion, etc.
            4. Parties Involved – ALL sellers/transferors and buyers/transferees
            5. Survey Number(s) affected
            6. Land Area Involved (with units)
            7. Any Government Orders or File References
            8. Outcome/Status - e.g., Approved, Rejected, Pending

            Pay special attention to:
            - All ENCUMBRANCES including loans, mortgages, liens, charges, and easements (બોજો)
            - Sale transactions (વેચાણ) with complete details of sellers and buyers
            - Loan entries (બોજોદાખલ) including lender name, borrower, loan amount, and property details
            - Removal of encumbrances (બોજા મુક્તિ) or loan satisfactions
            - Non-agricultural conversion orders (બીન ખેતી)
            - Mutation entries (નોંધ)
            - Land division/consolidation (ટુકડો/એકત્રીકરણ)
            - Court orders or collector decisions
            - Inheritance transfers



            ## Document Content to Analyze:
            {combined_text}

            ## FORMAT YOUR RESPONSE AS FOLLOWS:

            # CHAIN OF TITLE REPORT

            ## PROPERTY IDENTIFICATION
            - UPIN/Property ID: [Extract from document]
            - Survey/Block Number: [Current number]
            - Village/Town: [Extract from document]
            - Taluka/District: [Extract from document] 
            - Total Area: [With units]
            - Current Land Use: [Agricultural/Non-agricultural/Commercial, etc.]

            ## CHRONOLOGICAL CHAIN OF TITLE

            1. [EARLIEST ENTRY]
               Entry No: [Number]
               Date: [DD/MM/YYYY]
               Type: [Transaction type]
               From: [Previous owner(s)]
               To: [New owner(s)]
               Survey No: [Number(s)]
               Area: [Measurement with units]
               Reference: [Any file/order numbers]
               Details: [Brief description of transaction]
               Status: [Approved/Rejected/Pending]

            2. [SECOND ENTRY]
               [Same format as above]

            [Continue in chronological order for ALL entries]

            ## OWNERSHIP HIERARCHY DIAGRAM
            Prepare a clear and concise hierarchical representation of how ownership has transferred over time. Use this format:

            Original Owners: [Names]
                |
                | [Date] - [Type of Transfer]
                v
            Second Owners: [Names]
                |
                | [Date] - [Type of Transfer]
                v
            [Continue for each ownership change]
                |
                | [Date] - [Type of Transfer]
                v
            Current Owners: [Names]

            ## SALES TRANSACTIONS & LOAN ENTRIES
            List all sales transactions and loan entries separately in chronological order:

            ### Sales Transactions:
            1. Date: [DD/MM/YYYY] - Entry No: [Number]
            Seller: [Name(s)]
            Buyer: [Name(s)]
            Property: [Description]
            Amount: [Sale value if available]
            Status: [Approved/Rejected/Pending]
            
            ### Loan/Mortgage Entries:
            1. Date: [DD/MM/YYYY] - Entry No: [Number]
            Lender: [Financial institution/Person]
            Borrower: [Name(s)]
            Property: [Description]
            Loan Amount: [Value with currency]
            Status: [Active/Satisfied/Cancelled]

            ## CURRENT OWNERSHIP
            Based on the above chain of title, the current legal owner(s) of the property is/are [Names] as evidenced by Entry No. [Number] dated [Date].

            ## NOTABLE OBSERVATIONS
            -- [Any gaps or inconsistencies in documentation]
            - [Any encumbrances or restrictions on the property]
            - [Any rejected transactions and reasons]
            - [Any pending government orders or proceedings]
            - [Any other important observations]

            ## CHRONOLOGICAL HIERARCHY OF EVENTS

            • **DD/MM/YYYY:** [Construct a single comprehensive sentence that includes all details about this event - who transferred what to whom, the type of transaction, document references, property details, amounts, and official status. Format each event as a complete sentence that flows naturally despite containing multiple data points. Include parenthetical references for document numbers, dates, and clarifying information. End with the entry number reference.]

            • **DD/MM/YYYY:** [Next event in the same format]

            [Continue for all events in strict chronological order]


            """
            
            # Estimate tokens for this request (prompt + system message)
            system_message = "You are an expert legal document summarizer specializing in Indian land records and property documentation."
            estimated_tokens = self._estimate_tokens(prompt) + self._estimate_tokens(system_message)
            
            logger.debug(f"Estimated token usage for request: {estimated_tokens}")
            
            # Check rate limit
            wait_time = self._check_rate_limit(estimated_tokens)
            if wait_time > 0:
                # Wait until we can process this request
                logger.info(f"Rate limit reached. Waiting {wait_time:.2f}s before sending request.")
                await asyncio.sleep(wait_time)  # Using asyncio.sleep for async compatibility
            
            # Call OpenAI API with retry mechanism
            max_retries = 3
            backoff_factor = 2
            
            for attempt in range(max_retries):
                try:
                    logger.info(f"Sending request to OpenAI API (attempt {attempt + 1}/{max_retries})")
                    
                    response = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": system_message},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=16000,
                        temperature=0.1
                    )
                    
                    # Update token history with actual tokens used
                    tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
                    self._update_token_history(tokens_used)
                    
                    logger.info(f"OpenAI analysis completed successfully. Tokens used: {tokens_used}")
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
            
# Example usage:
# async def main():
#     service = LLMService()
#     result = await service.analyze_documents(["Your document text here"])
#     print(result)
# 
# if __name__ == "__main__":
#     asyncio.run(main())