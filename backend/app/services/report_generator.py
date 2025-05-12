from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
import logging
from .llm_service import LLMService
import os
import csv
import re
import json

# Set up logging
logger = logging.getLogger(__name__)

class ReportGenerator:
    """Service for generating title search reports"""
    
    def __init__(self):
        self.llm_service = LLMService()
        
    async def generate_report(self, 
                              document_texts: List[str]) -> Dict[str, Any]:
        """
        Generate a title search report from document texts
        
        Args:
            document_texts: List of extracted document texts
            
        Returns:
            Dict containing report data
        """
        # Validate inputs with better error handling
        if not document_texts:
            logger.error("Empty document_texts provided")
            raise ValueError("Document texts must be a non-empty list of strings")
            
        if not isinstance(document_texts, list):
            # Try to convert to list if it's not one
            try:
                logger.warning(f"Converting document_texts from {type(document_texts)} to list")
                document_texts = list(document_texts)
            except:
                logger.error(f"Could not convert document_texts of type {type(document_texts)} to list")
                raise ValueError("Document texts must be a non-empty list of strings")
        
        # Convert any non-string elements to strings
        processed_texts = []
        for text in document_texts:
            if not text:
                continue
            if not isinstance(text, str):
                logger.warning(f"Converting non-string document text of type {type(text)} to string")
                text = str(text)
            processed_texts.append(text)
        
        if not processed_texts:
            logger.error("No valid document texts found after processing")
            raise ValueError("No valid document texts found after processing")
            
        # Process with LLM - add error handling
        try:
            logger.info(f"Sending {len(processed_texts)} texts to LLM for analysis")
            report_content = await self.llm_service.analyze_documents(processed_texts)
            logger.info("LLM analysis completed successfully")
        except Exception as e:
            # Log the error and re-raise
            logger.error(f"LLM analysis failed: {str(e)}")
            raise ValueError(f"Failed to analyze documents: {str(e)}")
        
        # Create report object with only the fields we know exist in the database
        report_id = str(uuid.uuid4())
        report = {
            "id": report_id,
            "created_at": datetime.now().isoformat(),
            "content": report_content,
            "status": "completed"
        }
        
        # Extract title if possible, with better handling
        title_line = None
        if report_content:
            content_lines = report_content.split("\n")
            for line in content_lines[:10]:  # Only check first 10 lines
                if line and (line.strip().startswith("Re:") or line.strip().startswith("Re.:")): 
                    title_line = line.replace("Re:", "").replace("Re.:", "").strip()
                    break
        
        if title_line:
            report["title"] = f"Title Report - {title_line[:50]}"
        else:
            report["title"] = f"Title Report - {datetime.now().strftime('%Y-%m-%d')}"
            
        logger.info(f"Generated report with ID: {report_id}")
        return report
    
    def save_as_pdf(self, report: Dict[str, Any], output_path: str) -> str:
        """
        Save the report as a PDF with a 2-column table (heading, finding)
        
        Args:
            report: Report dictionary from generate_report
            output_path: Directory path to save the PDF file
            
        Returns:
            Path to the saved PDF file
        """
        try:
            # Attempt to import the required modules
            try:
                from reportlab.lib.pagesizes import letter
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib import colors
            except ImportError:
                logger.error("ReportLab package is not installed. Install it with: pip install reportlab")
                raise ImportError("ReportLab package is required for PDF generation. Install with: pip install reportlab")
            
            # Create filename from report title
            safe_title = "".join([c if c.isalnum() or c in " -_" else "_" for c in report["title"]])
            filename = f"{safe_title}_{report['id'][:8]}.pdf"
            file_path = os.path.join(output_path, filename)
            
            # Create PDF document
            doc = SimpleDocTemplate(file_path, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = []
            
            # Add title
            title = Paragraph(report["title"], styles["Title"])
            elements.append(title)
            elements.append(Spacer(1, 12))
            
            # Add metadata
            elements.append(Paragraph(f"Report ID: {report['id']}", styles["Normal"]))
            elements.append(Paragraph(f"Created: {report['created_at']}", styles["Normal"]))
            elements.append(Paragraph(f"Status: {report['status']}", styles["Normal"]))
            elements.append(Spacer(1, 24))
            
            # Extract table data
            table_data = self._extract_table_data(report["content"])
            
            # Create table for PDF
            pdf_table_data = [["Heading", "Finding"]]  # Header row
            for row in table_data:
                pdf_table_data.append([row.get("Heading", ""), row.get("Finding", "")])
            
            # Create table with appropriate styling
            table = Table(pdf_table_data, colWidths=[200, 300])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (1, 0), 14),
                ('BOTTOMPADDING', (0, 0), (1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            
            elements.append(table)
            
            # Build PDF
            doc.build(elements)
            logger.info(f"Saved report as PDF to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save report as PDF: {str(e)}")
            raise ValueError(f"PDF generation failed: {str(e)}")
    
    def save_as_table(self, report: Dict[str, Any], output_path: str, format: str = "csv") -> str:
        """
        Save the report in tabular format (CSV or Excel)
        
        Args:
            report: Report dictionary from generate_report
            output_path: Directory path to save the file
            format: Either 'csv' or 'excel'
            
        Returns:
            Path to the saved file
        """
        try:
            # Create filename from report title
            safe_title = "".join([c if c.isalnum() or c in " -_" else "_" for c in report["title"]])
            
            # Parse content to create structured data
            table_data = self._extract_table_data(report["content"])
            
            if format.lower() == "csv":
                filename = f"{safe_title}_{report['id'][:8]}.csv"
                file_path = os.path.join(output_path, filename)
                
                # Write CSV using built-in csv module
                with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['Heading', 'Finding']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in table_data:
                        writer.writerow(row)
                
            elif format.lower() == "excel":
                try:
                    import pandas as pd
                    
                    filename = f"{safe_title}_{report['id'][:8]}.xlsx"
                    file_path = os.path.join(output_path, filename)
                    
                    # Create DataFrame and save to Excel
                    df = pd.DataFrame(table_data)
                    df.to_excel(file_path, index=False)
                    
                except ImportError:
                    logger.warning("Pandas not installed. Falling back to CSV format.")
                    filename = f"{safe_title}_{report['id'][:8]}.csv"
                    file_path = os.path.join(output_path, filename)
                    
                    # Write CSV using built-in csv module
                    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                        fieldnames = ['Heading', 'Finding']
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        for row in table_data:
                            writer.writerow(row)
                    
                    logger.info("Excel format requested but pandas not installed. Saved as CSV instead.")
            else:
                raise ValueError(f"Unsupported table format: {format}")
                
            logger.info(f"Saved report as {format} to {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save report as table: {str(e)}")
            raise ValueError(f"Table generation failed: {str(e)}")
    
    def _extract_table_data(self, content: str) -> List[Dict[str, str]]:
        """
        Extract structured data from report content into a 2-column table format
        with headings on the left and findings on the right
        
        Args:
            content: Report content text
            
        Returns:
            List of dictionaries with 'Heading' and 'Finding' keys
        """
        table_data = []
        lines = content.split("\n")
        
        # Skip title and metadata at the beginning
        start_index = 0
        for i, line in enumerate(lines):
            if line.strip() == "":  # First empty line after metadata
                start_index = i + 1
                break
        
        current_heading = None
        current_finding = []
        
        # Pattern to identify heading lines (customize based on actual format)
        # For example, headings might be in ALL CAPS, or end with a colon
        heading_pattern = re.compile(r'^[A-Z][^:]+:$|^[A-Z ]{3,}$')
        
        i = start_index
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines
            if not line:
                i += 1
                continue
            
            # Check if this is a heading line
            if heading_pattern.match(line) or (len(line) <= 50 and (line.isupper() or line.endswith(':'))):
                # If we already have a heading and finding, save them
                if current_heading and current_finding:
                    table_data.append({
                        "Heading": current_heading,
                        "Finding": "\n".join(current_finding)
                    })
                
                # Start a new heading-finding pair
                current_heading = line.rstrip(':')
                current_finding = []
                
            else:
                # This is part of the finding for the current heading
                if current_heading:
                    current_finding.append(line)
                # If no current heading, this might be part of the introduction
                # Just skip or handle as needed
            
            i += 1
        
        # Add the last heading-finding pair if exists
        if current_heading and current_finding:
            table_data.append({
                "Heading": current_heading,
                "Finding": "\n".join(current_finding)
            })
        
        logger.info(f"Extracted {len(table_data)} heading-finding pairs from report content")
        return table_data