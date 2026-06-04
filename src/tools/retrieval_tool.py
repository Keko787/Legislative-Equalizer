"""
Retrieval tool for the Legal Assistant Agent.
Handles document retrieval and clause extraction using vector search.
"""

from typing import Dict, Any, List, Optional
from langchain_core.tools import BaseTool
from langchain_core.documents import Document
from pydantic import BaseModel, Field, ConfigDict
import json

from ..utils.vector_store import VectorStoreManager


class RetrievalInput(BaseModel):
    """Input schema for the retrieval tool."""
    query: str = Field(description="The search query or question about the document")
    clause_type: Optional[str] = Field(
        default=None,
        description="Specific type of clause to search for (e.g., 'termination', 'liability', 'payment')"
    )
    num_results: int = Field(default=5, description="Number of results to retrieve")


class RetrievalTool(BaseTool):
    """Tool for retrieving relevant document sections and clauses."""
    
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='allow')

    name: str = "document_retriever"
    description: str = """Retrieve relevant sections from legal documents based on user queries.
    This tool can:
    1. Search for specific clauses (termination, liability, payment terms, etc.)
    2. Find relevant sections for general questions
    3. Extract context for legal questions

    Use this tool when the user asks about:
    - Specific clauses or provisions
    - Document contents
    - Legal terms and conditions
    - Contract details
    """
    args_schema: type = RetrievalInput

    def __init__(self, vector_store_manager: VectorStoreManager):
        """Initialize the retrieval tool.

        Args:
            vector_store_manager: Vector store manager instance
        """
        super().__init__()
        object.__setattr__(self, 'vector_store_manager', vector_store_manager)

    def _run(self, query: str, clause_type: Optional[str] = None, num_results: int = 5) -> str:
        """Execute the retrieval operation.

        Args:
            query: Search query
            clause_type: Optional specific clause type to search for
            num_results: Number of results to retrieve

        Returns:
            Retrieved document sections as formatted string
        """
        try:
            # If clause type is specified, use targeted search
            if clause_type:
                documents = self.vector_store_manager.search_by_clause_type(
                    clause_type, k=num_results
                )
            else:
                # General similarity search
                documents = self.vector_store_manager.similarity_search(
                    query, k=num_results
                )

            if not documents:
                return "No relevant documents found for the query."

            # Format the results
            formatted_results = self._format_results(documents, query)
            return formatted_results

        except Exception as e:
            return f"Error retrieving documents: {str(e)}"

    async def _arun(self, query: str, clause_type: Optional[str] = None, num_results: int = 5) -> str:
        """Async version of the run method."""
        return self._run(query, clause_type, num_results)

    def _format_results(self, documents: List[Document], query: str) -> str:
        """Format retrieved documents for the agent.

        Args:
            documents: List of retrieved documents
            query: Original search query

        Returns:
            Formatted string with retrieved content
        """
        if not documents:
            return "No relevant sections found."

        result_parts = [
            f"Found {len(documents)} relevant sections for query: '{query}'\n",
            "=" * 60
        ]

        for i, doc in enumerate(documents, 1):
            metadata = doc.metadata
            source = metadata.get('source', 'Unknown')
            chunk_id = metadata.get('chunk_id', 'N/A')
            potential_clauses = metadata.get('potential_clauses', [])

            result_parts.append(f"\n📄 SECTION {i}")
            result_parts.append(f"Source: {source} (Chunk {chunk_id})")

            if potential_clauses:
                result_parts.append(f"Identified Clauses: {', '.join(potential_clauses)}")

            result_parts.append("Content:")
            result_parts.append("-" * 40)
            result_parts.append(doc.page_content.strip())
            result_parts.append("-" * 40)

        return "\n".join(result_parts)

    def search_specific_terms(self, terms: List[str], max_results_per_term: int = 3) -> Dict[str, List[Document]]:
        """Search for multiple specific terms.

        Args:
            terms: List of terms to search for
            max_results_per_term: Maximum results per search term

        Returns:
            Dictionary mapping terms to their search results
        """
        results = {}

        for term in terms:
            try:
                docs = self.vector_store_manager.similarity_search(
                    term, k=max_results_per_term
                )
                results[term] = docs
            except Exception as e:
                results[term] = []

        return results

    def get_clause_summary(self, clause_type: str) -> str:
        """Get a summary of all instances of a specific clause type.

        Args:
            clause_type: Type of clause to summarize

        Returns:
            Summary of clause instances
        """
        try:
            documents = self.vector_store_manager.search_by_clause_type(clause_type, k=10)

            if not documents:
                return f"No {clause_type} clauses found in the document."

            summary_parts = [
                f"📋 SUMMARY: {clause_type.upper()} CLAUSES",
                "=" * 50,
                f"Found {len(documents)} relevant sections:\n"
            ]

            for i, doc in enumerate(documents, 1):
                # Extract key information from each clause
                content = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
                summary_parts.append(f"{i}. {content}\n")

            return "\n".join(summary_parts)

        except Exception as e:
            return f"Error generating clause summary: {str(e)}"

    def compare_clauses(self, clause_types: List[str]) -> str:
        """Compare multiple types of clauses.

        Args:
            clause_types: List of clause types to compare

        Returns:
            Comparison summary
        """
        if len(clause_types) < 2:
            return "Need at least 2 clause types for comparison."

        comparison_results = {}
        for clause_type in clause_types:
            docs = self.vector_store_manager.search_by_clause_type(clause_type, k=3)
            comparison_results[clause_type] = docs

        # Format comparison
        comparison_parts = [
            "🔍 CLAUSE COMPARISON",
            "=" * 50
        ]

        for clause_type, docs in comparison_results.items():
            comparison_parts.append(f"\n📋 {clause_type.upper()} CLAUSES:")
            comparison_parts.append("-" * 30)

            if docs:
                for doc in docs[:2]:  # Show top 2 results
                    content = doc.page_content[:150] + "..." if len(doc.page_content) > 150 else doc.page_content
                    comparison_parts.append(f"• {content}")
            else:
                comparison_parts.append("• No relevant clauses found")

        return "\n".join(comparison_parts)