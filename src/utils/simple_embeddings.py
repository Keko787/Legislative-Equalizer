"""
Simple embeddings implementation to avoid heavy dependencies.
Uses basic text similarity for demonstration purposes.
"""

import numpy as np
from typing import List
import re
from collections import Counter
import math


class SimpleEmbeddings:
    """Simple text embedding using TF-IDF approach."""

    def __init__(self):
        self.vocabulary = {}
        self.idf_values = {}
        self.documents = []

    def _preprocess_text(self, text: str) -> List[str]:
        """Basic text preprocessing."""
        # Convert to lowercase and extract words
        text = text.lower()
        # Remove special characters and split
        words = re.findall(r'\b[a-zA-Z]+\b', text)
        return words

    def _compute_tf(self, text: str) -> dict:
        """Compute term frequency."""
        words = self._preprocess_text(text)
        word_count = len(words)
        tf_dict = {}
        for word in words:
            tf_dict[word] = tf_dict.get(word, 0) + 1
        # Normalize by document length
        for word in tf_dict:
            tf_dict[word] = tf_dict[word] / word_count
        return tf_dict

    def _compute_idf(self, documents: List[str]) -> dict:
        """Compute inverse document frequency."""
        N = len(documents)
        all_words = set()
        for doc in documents:
            words = self._preprocess_text(doc)
            all_words.update(words)

        idf_dict = {}
        for word in all_words:
            containing_docs = sum(1 for doc in documents if word in self._preprocess_text(doc))
            idf_dict[word] = math.log(N / containing_docs) if containing_docs > 0 else 0

        return idf_dict

    def fit(self, documents: List[str]):
        """Fit the embeddings model on documents."""
        self.documents = documents
        self.idf_values = self._compute_idf(documents)

        # Build vocabulary
        all_words = set()
        for doc in documents:
            words = self._preprocess_text(doc)
            all_words.update(words)

        self.vocabulary = {word: idx for idx, word in enumerate(sorted(all_words))}

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Convert texts to embeddings."""
        embeddings = []

        for text in texts:
            tf_dict = self._compute_tf(text)
            # Create vector based on vocabulary
            vector = [0.0] * len(self.vocabulary)

            for word, tf_value in tf_dict.items():
                if word in self.vocabulary:
                    idx = self.vocabulary[word]
                    idf_value = self.idf_values.get(word, 0)
                    vector[idx] = tf_value * idf_value

            embeddings.append(vector)

        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """Convert single query to embedding."""
        return self.embed_documents([text])[0]


class SimpleVectorStore:
    """Simple vector store for similarity search."""

    def __init__(self):
        self.embeddings_model = SimpleEmbeddings()
        self.documents = []
        self.vectors = []

    def add_documents(self, documents):
        """Add documents to the vector store."""
        self.documents = documents
        texts = [doc.page_content for doc in documents]

        # Fit embeddings model
        self.embeddings_model.fit(texts)

        # Generate embeddings
        self.vectors = self.embeddings_model.embed_documents(texts)

    def similarity_search(self, query: str, k: int = 5) -> List:
        """Perform similarity search."""
        if not self.vectors:
            return []

        # Get query embedding
        query_vector = self.embeddings_model.embed_query(query)

        # Calculate cosine similarity
        similarities = []
        for i, doc_vector in enumerate(self.vectors):
            similarity = self._cosine_similarity(query_vector, doc_vector)
            similarities.append((similarity, i))

        # Sort by similarity and return top k
        similarities.sort(reverse=True)

        results = []
        for similarity, idx in similarities[:k]:
            if similarity > 0.01:  # Minimum similarity threshold
                results.append(self.documents[idx])

        return results

    def similarity_search_with_score(self, query: str, k: int = 5):
        """Perform similarity search with scores."""
        if not self.vectors:
            return []

        # Get query embedding
        query_vector = self.embeddings_model.embed_query(query)

        # Calculate cosine similarity
        similarities = []
        for i, doc_vector in enumerate(self.vectors):
            similarity = self._cosine_similarity(query_vector, doc_vector)
            similarities.append((similarity, i))

        # Sort by similarity and return top k
        similarities.sort(reverse=True)

        results = []
        for similarity, idx in similarities[:k]:
            if similarity > 0.01:  # Minimum similarity threshold
                results.append((self.documents[idx], similarity))

        return results

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not vec1 or not vec2:
            return 0.0

        # Convert to numpy arrays for easier computation
        a = np.array(vec1)
        b = np.array(vec2)

        # Calculate dot product
        dot_product = np.dot(a, b)

        # Calculate magnitudes
        magnitude_a = np.linalg.norm(a)
        magnitude_b = np.linalg.norm(b)

        # Avoid division by zero
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    def save_local(self, path: str):
        """Save the vector store (placeholder for compatibility)."""
        pass

    def load_local(self, path: str):
        """Load the vector store (placeholder for compatibility)."""
        pass