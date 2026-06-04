"""
Document processing utilities for the Legal Assistant Agent.
Handles PDF upload, text extraction, and preprocessing for clause retrieval.
"""

import os
import re
import tempfile
from typing import List, Dict, Any
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document


class DocumentProcessor:
    """Handles document processing for legal documents."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """Initialize the document processor.

        Args:
            chunk_size: Size of text chunks for splitting
            chunk_overlap: Overlap between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )

    def extract_text_from_pdf(self, pdf_file) -> str:
        """Extract text from uploaded PDF file.

        Args:
            pdf_file: Streamlit uploaded file object

        Returns:
            Extracted text content
        """
        try:
            # Save uploaded file to temporary location
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                tmp_file.write(pdf_file.getbuffer())
                tmp_path = tmp_file.name

            # Extract text using pypdf
            reader = PdfReader(tmp_path)
            text = ""

            for page in reader.pages:
                page_text = page.extract_text()
                text += page_text + "\n"

            # Clean up temporary file
            os.unlink(tmp_path)

            return text.strip()

        except Exception as e:
            raise Exception(f"Error extracting text from PDF: {str(e)}")

    def preprocess_text(self, text: str) -> str:
        """Clean and preprocess extracted text.

        Preserves paragraph structure (newlines) so downstream segmenters
        can identify section boundaries. Only collapses runs of horizontal
        whitespace.
        """
        # Strip control / replacement chars first
        text = text.replace('\x00', '').replace('\ufffd', '')
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        # Collapse runs of horizontal whitespace (spaces, tabs)
        text = re.sub(r'[ \t]+', ' ', text)
        # Trim spaces around newlines
        text = re.sub(r' *\n *', '\n', text)
        # Collapse 3+ consecutive newlines to a paragraph break
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def split_into_chunks(self, text: str, source: str = "document") -> List[Document]:
        """Split text into chunks for vector storage.

        Args:
            text: Preprocessed text content
            source: Source identifier for the document

        Returns:
            List of Document objects with metadata
        """
        preprocessed_text = self.preprocess_text(text)
        chunks = self.text_splitter.split_text(preprocessed_text)

        documents = []
        for i, chunk in enumerate(chunks):
            doc = Document(
                page_content=chunk,
                metadata={
                    "source": source,
                    "chunk_id": i,
                    "chunk_size": len(chunk)
                }
            )
            documents.append(doc)

        return documents

    def process_pdf(self, pdf_file, filename: str = None) -> List[Document]:
        """Complete processing pipeline for PDF documents.

        Args:
            pdf_file: Streamlit uploaded file object
            filename: Optional filename for metadata

        Returns:
            List of processed Document objects
        """
        if filename is None:
            filename = getattr(pdf_file, 'name', 'unknown_document.pdf')

        # Extract text
        raw_text = self.extract_text_from_pdf(pdf_file)

        if not raw_text.strip():
            raise ValueError("No text could be extracted from the PDF")

        # Split into chunks
        documents = self.split_into_chunks(raw_text, source=filename)

        return documents

    def identify_clauses(self, documents: List[Document]) -> List[Document]:
        """Identify and tag potential legal clauses in documents.

        Args:
            documents: List of document chunks

        Returns:
            Documents with enhanced metadata for clause identification
        """
        # Common legal clause indicators
        clause_indicators = [
            "termination", "notice", "liability", "indemnification",
            "confidentiality", "non-disclosure", "payment terms",
            "force majeure", "governing law", "dispute resolution",
            "intellectual property", "warranties", "representations"
        ]

        enhanced_docs = []

        for doc in documents:
            content_lower = doc.page_content.lower()
            identified_clauses = []

            for indicator in clause_indicators:
                if indicator in content_lower:
                    identified_clauses.append(indicator)

            # Update metadata
            doc.metadata.update({
                "potential_clauses": identified_clauses,
                "clause_count": len(identified_clauses)
            })

            enhanced_docs.append(doc)

        return enhanced_docs


def create_sample_contract() -> str:
    """Create a sample legal contract for demo purposes."""
    return """
    PROFESSIONAL SERVICES AGREEMENT

    This Professional Services Agreement ("Agreement") is entered into on [DATE] between Company ABC ("Client") and Service Provider XYZ ("Provider").

    1. SCOPE OF WORK
    Provider agrees to perform consulting services as detailed in Exhibit A attached hereto.

    2. PAYMENT TERMS
    Client shall pay Provider a total fee of $50,000 payable in monthly installments of $10,000.
    Payment is due within 30 days of invoice receipt.

    3. TERMINATION CLAUSE
    Either party may terminate this Agreement with thirty (30) days written notice to the other party.
    In case of material breach, the non-breaching party may terminate immediately upon written notice.

    4. CONFIDENTIALITY
    Both parties agree to maintain confidentiality of all proprietary information exchanged during the term of this Agreement.
    This confidentiality obligation shall survive termination of this Agreement for a period of three (3) years.

    5. LIABILITY AND INDEMNIFICATION
    Provider's total liability under this Agreement shall not exceed the total fees paid by Client.
    Each party agrees to indemnify the other against third-party claims arising from their negligent acts.

    6. INTELLECTUAL PROPERTY
    All work products created by Provider shall be owned by Client upon full payment of fees.
    Provider retains ownership of its pre-existing intellectual property and general methodologies.

    7. FORCE MAJEURE
    Neither party shall be liable for delays caused by circumstances beyond their reasonable control,
    including natural disasters, government actions, or pandemic-related restrictions.

    8. GOVERNING LAW
    This Agreement shall be governed by the laws of [STATE] without regard to conflict of law principles.
    Any disputes shall be resolved through binding arbitration in [CITY], [STATE].

    9. NOTICE PROVISIONS
    All notices must be in writing and delivered via certified mail or email with read receipt.
    Notice to Client: legal@companyabc.com
    Notice to Provider: contracts@servicexproviderxyz.com

    10. MISCELLANEOUS
    This Agreement constitutes the entire agreement between the parties.
    Any modifications must be in writing and signed by both parties.
    """