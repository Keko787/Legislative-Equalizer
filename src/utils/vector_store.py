"""
Vector store management for the Legal Assistant Agent.
Handles FAISS vector database operations for document retrieval.
"""

import os
import pickle
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
try:
    from langchain_community.vectorstores import FAISS
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

try:
    from langchain.embeddings import HuggingFaceEmbeddings
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

# Import SimpleVectorStore regardless of FAISS availability for fallback
try:
    from .simple_embeddings import SimpleVectorStore
    SIMPLE_AVAILABLE = True
except ImportError:
    SIMPLE_AVAILABLE = False


class VectorStoreManager:
    """Manages FAISS vector store for document retrieval."""

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2", persist_directory: str = "data/vectorstore"):
        """Initialize the vector store manager.

        Args:
            embedding_model: HuggingFace embedding model name
            persist_directory: Directory to persist the vector store
        """
        self.embedding_model_name = embedding_model
        self.persist_directory = persist_directory

        global FAISS_AVAILABLE, EMBEDDINGS_AVAILABLE
        if FAISS_AVAILABLE and EMBEDDINGS_AVAILABLE:
            try:
                self.embeddings = HuggingFaceEmbeddings(
                    model_name=embedding_model,
                    model_kwargs={'device': 'cpu'},
                    encode_kwargs={'normalize_embeddings': True}
                )
            except Exception:
                # If HuggingFace embeddings fail, use simple embeddings
                self.embeddings = None
                FAISS_AVAILABLE = False
        else:
            self.embeddings = None

        self.vectorstore = None

        # Create persist directory if it doesn't exist
        os.makedirs(persist_directory, exist_ok=True)

    def create_vectorstore(self, documents: List[Document]):
        """Create a new vector store from documents.

        Args:
            documents: List of Document objects to index

        Returns:
            Vector store instance
        """
        if not documents:
            raise ValueError("Cannot create vector store with empty document list")

        global FAISS_AVAILABLE
        if FAISS_AVAILABLE and self.embeddings:
            self.vectorstore = FAISS.from_documents(
                documents=documents,
                embedding=self.embeddings
            )
        else:
            # Use simple vector store
            global SIMPLE_AVAILABLE
            if SIMPLE_AVAILABLE:
                self.vectorstore = SimpleVectorStore()
                self.vectorstore.add_documents(documents)
            else:
                raise RuntimeError("Neither FAISS nor SimpleVectorStore is available. Please install required dependencies.")

        return self.vectorstore

    def add_documents(self, documents: List[Document]) -> None:
        """Add new documents to existing vector store.

        Args:
            documents: List of Document objects to add
        """
        if not self.vectorstore:
            self.create_vectorstore(documents)
        else:
            self.vectorstore.add_documents(documents)

    def similarity_search(self, query: str, k: int = 5, score_threshold: float = 0.0) -> List[Document]:
        """Perform similarity search in the vector store.

        Args:
            query: Search query
            k: Number of results to return
            score_threshold: Minimum similarity score threshold

        Returns:
            List of relevant documents
        """
        if not self.vectorstore:
            return []

        global FAISS_AVAILABLE
        if FAISS_AVAILABLE and hasattr(self.vectorstore, 'similarity_search_with_score'):
            # Use FAISS similarity search with score
            docs_with_scores = self.vectorstore.similarity_search_with_score(query, k=k)
            # Filter by score threshold
            filtered_docs = [
                doc for doc, score in docs_with_scores
                if score >= score_threshold
            ]
            return filtered_docs
        else:
            # Use simple vector store
            return self.vectorstore.similarity_search(query, k=k)

    def search_by_clause_type(self, clause_type: str, k: int = 3) -> List[Document]:
        """Search for specific types of legal clauses.

        Args:
            clause_type: Type of clause to search for (e.g., "termination", "liability")
            k: Number of results to return

        Returns:
            List of relevant clause documents
        """
        # Create query variants for better matching
        query_variants = [
            clause_type,
            f"{clause_type} clause",
            f"{clause_type} provision",
            f"{clause_type} terms"
        ]

        all_results = []
        for query in query_variants:
            results = self.similarity_search(query, k=k//len(query_variants) + 1)
            all_results.extend(results)

        # Remove duplicates and return top k
        unique_results = []
        seen_content = set()

        for doc in all_results:
            content_hash = hash(doc.page_content)
            if content_hash not in seen_content:
                unique_results.append(doc)
                seen_content.add(content_hash)

            if len(unique_results) >= k:
                break

        return unique_results

    def get_relevant_context(self, query: str, max_tokens: int = 2000) -> str:
        """Get relevant context for a query, respecting token limits.

        Args:
            query: Search query
            max_tokens: Maximum number of tokens in response

        Returns:
            Concatenated relevant text content
        """
        docs = self.similarity_search(query, k=10)

        context_parts = []
        current_length = 0

        for doc in docs:
            content = doc.page_content
            # Rough token estimation (1 token ≈ 4 characters)
            estimated_tokens = len(content) // 4

            if current_length + estimated_tokens <= max_tokens:
                context_parts.append(content)
                current_length += estimated_tokens
            else:
                # Add partial content if there's room
                remaining_chars = (max_tokens - current_length) * 4
                if remaining_chars > 100:  # Only add if meaningful amount
                    context_parts.append(content[:remaining_chars])
                break

        return "\n\n".join(context_parts)

    def save_vectorstore(self, path: Optional[str] = None) -> str:
        """Save the vector store to disk.

        Args:
            path: Optional custom path to save

        Returns:
            Path where vectorstore was saved
        """
        if not self.vectorstore:
            raise ValueError("No vector store to save")

        save_path = path or os.path.join(self.persist_directory, "faiss_index")
        self.vectorstore.save_local(save_path)

        return save_path

    def load_vectorstore(self, path: Optional[str] = None) -> FAISS:
        """Load a vector store from disk.

        Args:
            path: Optional custom path to load from

        Returns:
            Loaded FAISS vector store instance
        """
        load_path = path or os.path.join(self.persist_directory, "faiss_index")

        if not os.path.exists(load_path):
            raise FileNotFoundError(f"Vector store not found at {load_path}")

        self.vectorstore = FAISS.load_local(
            load_path,
            self.embeddings,
            allow_dangerous_deserialization=True
        )

        return self.vectorstore

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector store.

        Returns:
            Dictionary with vector store statistics
        """
        if not self.vectorstore:
            return {"status": "not_initialized"}

        global FAISS_AVAILABLE
        if FAISS_AVAILABLE and hasattr(self.vectorstore, 'index_to_docstore_id'):
            return {
                "status": "initialized",
                "total_documents": len(self.vectorstore.index_to_docstore_id),
                "embedding_dimension": getattr(self.vectorstore.index, 'd', 'unknown'),
                "embedding_model": self.embedding_model_name,
            }
        else:
            return {
                "status": "initialized",
                "total_documents": len(getattr(self.vectorstore, 'documents', [])),
                "embedding_dimension": "simple_tf_idf",
                "embedding_model": "simple_embeddings",
            }

    def reset_vectorstore(self) -> None:
        """Reset the vector store (clear all data)."""
        self.vectorstore = None

        # Clean up persisted data
        import shutil
        faiss_path = os.path.join(self.persist_directory, "faiss_index")
        if os.path.exists(faiss_path):
            shutil.rmtree(faiss_path)