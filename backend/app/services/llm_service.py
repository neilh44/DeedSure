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
        self.model = os.environ.get("LLM_MODEL", "gpt-4o")  # Default to GPT-4o if not specified
        
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
            You are an expert legal document analyzer with deep knowledge of Indian land records, property law, and title examination. Given the following land record or mutation register (7/12 extract, Property Card, etc.), extract and present a COMPREHENSIVE TITLE EXAMINATION REPORT in a structured format.

            ## KEY INSTRUCTIONS:
            Extract and organize ALL information that affects property rights, ownership, encumbrances, and legal status in CHRONOLOGICAL ORDER (oldest to newest).

            For each entry in the chain of title, identify and include:
            1. Entry/Memo Number (નોધ નંબર) 
            2. Entry Date (નોધની તારીખ) - format as DD/MM/YYYY
            3. Type of Change (ફેરફારનો પ્રકાર) - e.g., sale, inheritance, conversion, court order, etc.
            4. Parties Involved – ALL sellers/transferors and buyers/transferees with COMPLETE names and identification details
            5. Survey Number(s) affected, including any changes or subdivisions
            6. Land Area Involved (with exact units and measurements)
            7. Any Government Orders, File References, Case Numbers, or Administrative Proceedings
            8. Outcome/Status - e.g., Approved, Rejected, Pending, Contested
            9. Official who verified/approved the entry
            10. Any conditions or restrictions imposed

            Pay special attention to:
            - ALL ENCUMBRANCES including loans, mortgages, liens, charges, easements, and restrictive covenants (બોજો)
            - Sale transactions (વેચાણ) with complete details including consideration amounts and payment methods
            - Loan entries (બોજોદાખલ) including lender name, borrower, loan amount, terms, and security details
            - Removal of encumbrances (બોજા મુક્તિ) or loan satisfactions
            - Non-agricultural conversion orders (બીન ખેતી) including premium payments and conditions
            - Mutation entries (નોંધ) and their basis
            - Land division/consolidation (ટુકડો/એકત્રીકરણ) with details of resulting parcels
            - Court orders, collector decisions, or administrative appeals
            - Inheritance transfers with details of succession documents
            - Town Planning Scheme inclusions or modifications
            - Development restrictions or permissions
            - Discrepancies between entries or inconsistencies in the records
            - Missing documentation references or gaps in the chain of title
            - Any notations of disputes or objections raised

            ## FORMAT YOUR RESPONSE AS FOLLOWS:

            # COMPREHENSIVE TITLE EXAMINATION REPORT

            ## PROPERTY IDENTIFICATION
            - UPIN/Property ID: [Extract from document]
            - Survey/Block Number: [Current number with history of changes]
            - Village/Town: [Extract from document]
            - Taluka/District: [Extract from document] 
            - Total Area: [With units and any history of changes]
            - Current Land Use: [Agricultural/Non-agricultural/Commercial, etc.]
            - Land Classification: [Old/New Tenure, Restricted, etc.]
            - Assessment/Tax Details: [If available]
            - Boundaries/Adjacent Properties: [If mentioned]
            - Any Town Planning Scheme details: [TP Number, Final Plot Number]

            ## CHRONOLOGICAL CHAIN OF TITLE

            1. [EARLIEST ENTRY]
            Entry No: [Number]
            Date: [DD/MM/YYYY]
            Type: [Transaction type]
            From: [Previous owner(s) with complete identification]
            To: [New owner(s) with complete identification]
            Survey No: [Number(s)]
            Area: [Measurement with units]
            Reference: [Any file/order numbers]
            Details: [Comprehensive description of transaction]
            Conditions: [Any conditions imposed]
            Status: [Approved/Rejected/Pending]
            Verified By: [Official name and designation]
            Comments: [Any notable aspects of this entry]

            2. [SECOND ENTRY]
            [Same format as above]

            [Continue in chronological order for ALL entries]

            ## OWNERSHIP HIERARCHY DIAGRAM
            Create a detailed hierarchical representation showing all ownership transfers, including partial interests when applicable:

            Original Owners: [Names with percentage interests if divided]
                |
                | [Date] - [Type of Transfer with details]
                v
            Second Owners: [Names with percentage interests if divided]
                |
                | [Date] - [Type of Transfer with details]
                v
            [Continue for each ownership change]
                |
                | [Date] - [Type of Transfer with details]
                v
            Current Owners: [Names with percentage interests if divided]

            ## LAND USE TRANSFORMATION HISTORY
            Chronological listing of all land use changes:
            1. Date: [DD/MM/YYYY] - Entry No: [Number]
            Original Classification: [e.g., Agricultural]
            New Classification: [e.g., Non-agricultural Residential]
            Authority: [Who approved the change]
            Conditions: [Special conditions imposed]
            Premium Paid: [Amount if applicable]
            Annual Assessment: [New tax/assessment amount]

            ## SALES TRANSACTIONS & CONSIDERATION DETAILS
            List all sales transactions with complete financial information:

            1. Date: [DD/MM/YYYY] - Entry No: [Number]
            Seller: [Name(s) with complete identification]
            Buyer: [Name(s) with complete identification]
            Property Description: [Survey numbers, area, etc.]
            Consideration Amount: [Sale value with currency]
            Method of Payment: [If mentioned]
            Stamp Duty Paid: [If available]
            Registration Details: [Document number, registration office]
            Special Conditions: [Any conditions in the sale deed]
            Status: [Approved/Rejected/Pending]

            ## ENCUMBRANCES HISTORY
            Chronological listing of all encumbrances and their current status:

            1. Date Created: [DD/MM/YYYY] - Entry No: [Number]
            Type: [Mortgage/Lien/Charge/Easement]
            In Favor Of: [Lender/Beneficiary]
            Against: [Property owner/Borrower]
            Property Affected: [Description]
            Amount: [Value with currency]
            Terms: [Duration, interest rate if available]
            Current Status: [Active/Satisfied/Cancelled]
            Date Satisfied: [If applicable]
            Entry No of Satisfaction: [If applicable]

            ## LEGAL PROCEEDINGS & DISPUTES
            Chronological account of all legal cases, disputes, and administrative proceedings:

            1. Date Initiated: [DD/MM/YYYY]
            Type of Proceeding: [Civil Suit/Appeal/Administrative Review]
            Case Number: [With court/tribunal name]
            Parties: [Plaintiffs and Defendants]
            Regarding: [Subject matter]
            Current Status: [Pending/Resolved/Appealed]
            Outcome: [Decision summary]
            Impact on Title: [How this affects ownership/rights]

            ## GOVERNMENT ORDERS & ADMINISTRATIVE ACTIONS
            List of all significant government interventions affecting the property:

            1. Date: [DD/MM/YYYY] - Order No: [Reference]
            Issuing Authority: [Name and designation]
            Type of Order: [Conversion/Regularization/Acquisition/etc.]
            Regarding: [Subject matter]
            Effect on Property: [Rights modified/restricted/granted]
            Conditions Imposed: [List of conditions]
            Compliance Status: [Complied/Pending/Violated]

            ## TOWN PLANNING IMPACTS
            Details of Town Planning Schemes affecting the property:

            - Original Survey Number: [Number]
            - TP Scheme Number: [Number]
            - Final Plot Number: [Number]
            - Original Area: [Measurement]
            - Final Plot Area: [Measurement]
            - Deduction Percentage: [If applicable]
            - Land Use Zoning: [As per TP Scheme]
            - Development Restrictions: [FSI/Height/Setbacks/etc.]
            - Infrastructure Charges Paid: [If mentioned]

            ## DOCUMENT VERIFICATION ANALYSIS
            Assessment of documentation completeness and authenticity:

            - Chain of Title Completeness: [Complete/Gaps Identified]
            - Missing Documents: [List any missing critical documents]
            - Documentation Discrepancies: [Identify any inconsistencies]
            - Authentication Issues: [Any concerns about document authenticity]
            - Record Keeping Anomalies: [Issues with record maintenance]

            ## CURRENT OWNERSHIP ANALYSIS
            Based on the above chain of title, analyze current ownership status:

            - Current Legal Owner(s): [Names with percentage interests]
            - Evidenced By: Entry No. [Number] dated [Date]
            - Nature of Ownership: [Absolute/Conditional/Leasehold/etc.]
            - Duration of Ownership: [Time period]
            - Restrictions on Rights: [Any limitations on owner's rights]
            - Possession Status: [Who currently possesses the property]

            ## RISK ASSESSMENT
            Evaluation of potential title risks:

            - Clear Title Rating: [Clear/Mostly Clear/Questionable/Clouded]
            - Major Title Risks: [List significant concerns]
            - Minor Title Issues: [List less significant issues]
            - Potential Future Complications: [Foreseeable problems]
            - Undocumented Rights: [Rights that may exist but aren't recorded]
            - Adverse Possession Risks: [If applicable]
            - Boundary Dispute Potential: [Assessment of boundary clarity]

            ## NOTABLE OBSERVATIONS
            - [Any gaps or inconsistencies in documentation]
            - [Any unusual patterns in transactions]
            - [Any rejected transactions and reasons]
            - [Any pending government orders or proceedings]
            - [Family relationships between parties that may affect title]
            - [Unusual valuation patterns]
            - [Frequency of transactions]
            - [Any other important observations]

            ## RECOMMENDATIONS
            Based on comprehensive analysis:

            - Title Insurance Recommendation: [Recommended/Not Recommended/Conditional]
            - Additional Documentation Needed: [List documents required to clarify title]
            - Suggested Legal Actions: [Steps to remedy any title defects]
            - Due Diligence Suggestions: [Additional investigations recommended]
            - Professional Consultations Required: [Legal/Survey/Technical expertise needed]
            - Special Precautions for Transactions: [Safeguards for future dealings]

            ## TIMELINE VISUALIZATION
            [Instructions to create a visual timeline representation of major events affecting the property]
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