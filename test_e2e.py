#!/usr/bin/env python3
"""
End-to-end test for the Legal Assistant Agent.
Tests core functionality without external dependencies.
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.utils.document_processor import DocumentProcessor, create_sample_contract
from src.utils.vector_store import VectorStoreManager
from src.memory.conversation_memory import ConversationMemory


def test_document_processing():
    """Test document processing pipeline."""
    print("1. Testing Document Processing...")

    processor = DocumentProcessor()

    # Test sample contract creation
    sample_contract = create_sample_contract()
    assert len(sample_contract) > 1000, "Sample contract should be substantial"
    print(f"   ✓ Sample contract created: {len(sample_contract)} characters")

    # Test text splitting
    documents = processor.split_into_chunks(sample_contract, "test_contract.pdf")
    assert len(documents) > 0, "Should create document chunks"
    print(f"   ✓ Document split into {len(documents)} chunks")

    # Test clause identification
    enhanced_docs = processor.identify_clauses(documents)
    assert len(enhanced_docs) == len(documents), "Should enhance all documents"

    # Count identified clauses
    total_clauses = sum(len(doc.metadata.get('potential_clauses', [])) for doc in enhanced_docs)
    assert total_clauses > 0, "Should identify some clauses"
    print(f"   ✓ Identified {total_clauses} legal clauses")

    return enhanced_docs


def test_vector_store(documents):
    """Test vector store functionality."""
    print("\n2. Testing Vector Store...")

    vector_manager = VectorStoreManager()

    # Test vector store creation
    vectorstore = vector_manager.create_vectorstore(documents)
    assert vectorstore is not None, "Should create vector store"
    print(f"   ✓ Vector store created successfully")

    # Test similarity search
    results = vector_manager.similarity_search("termination clause", k=3)
    assert len(results) > 0, "Should find relevant results"
    print(f"   ✓ Found {len(results)} results for 'termination clause'")

    # Test clause-specific search
    termination_results = vector_manager.search_by_clause_type("termination", k=2)
    print(f"   ✓ Found {len(termination_results)} termination-specific results")

    # Test stats
    stats = vector_manager.get_stats()
    assert stats['status'] == 'initialized', "Should be initialized"
    print(f"   ✓ Vector store stats: {stats['total_documents']} documents")

    return vector_manager


def test_memory():
    """Test conversation memory."""
    print("\n3. Testing Conversation Memory...")

    memory = ConversationMemory()

    # Test adding conversation turns
    memory.add_turn("What is the termination clause?", "Termination requires 30 days notice.", {})
    memory.add_turn("What about payment terms?", "Payment is due within 30 days.", {})

    history = memory.get_conversation_history()
    assert len(history) == 2, "Should store conversation turns"
    print(f"   ✓ Stored {len(history)} conversation turns")

    # Test context generation
    context = memory.get_context_for_query("Tell me about notice period")
    assert "termination" in context.lower(), "Should include relevant context"
    print(f"   ✓ Generated contextual information")

    # Test follow-up suggestions
    followup = memory.get_follow_up_context()
    assert 'topics_discussed' in followup, "Should track discussed topics"
    print(f"   ✓ Generated follow-up suggestions")

    return memory


def test_simple_legal_assistant():
    """Test the simplified legal assistant."""
    print("\n4. Testing Simple Legal Assistant...")

    # Import the simplified assistant
    sys.path.append('.')
    from app_simple import SimpleLegalAssistant

    assistant = SimpleLegalAssistant()

    # Test document processing
    num_chunks, success = assistant.process_document(use_sample=True)
    assert success, "Should successfully process sample document"
    assert num_chunks > 0, "Should create document chunks"
    print(f"   ✓ Processed sample document: {num_chunks} chunks")

    # Test queries
    queries = [
        "What is the termination clause?",
        "Tell me about payment terms",
        "Explain the liability section",
        "What are my obligations?"
    ]

    for query in queries:
        response = assistant.process_query(query)
        assert len(response) > 50, f"Should provide substantial response for '{query}'"
        print(f"   ✓ Answered: '{query[:30]}...'")

    # Test conversation history
    history = assistant.memory.get_conversation_history()
    assert len(history) == len(queries), "Should store all queries"
    print(f"   ✓ Stored {len(history)} conversation turns")

    return assistant


def test_search_functionality(assistant):
    """Test search functionality with various queries."""
    print("\n5. Testing Search Functionality...")

    search_queries = [
        ("termination", "Should find termination-related content"),
        ("payment", "Should find payment-related content"),
        ("confidentiality", "Should find confidentiality clauses"),
        ("liability", "Should find liability information"),
        ("intellectual property", "Should find IP clauses")
    ]

    for query, description in search_queries:
        results = assistant.search_document(query, num_results=2)
        assert "No relevant information" not in results, f"Should find content for '{query}'"
        assert len(results) > 100, f"Should provide substantial results for '{query}'"
        print(f"   ✓ {description}")

    return True


def main():
    """Run all end-to-end tests."""
    print("Legal Assistant Agent - End-to-End Tests")
    print("=" * 50)

    try:
        # Test 1: Document Processing
        documents = test_document_processing()

        # Test 2: Vector Store
        vector_manager = test_vector_store(documents)

        # Test 3: Memory
        memory = test_memory()

        # Test 4: Simple Legal Assistant
        assistant = test_simple_legal_assistant()

        # Test 5: Search Functionality
        test_search_functionality(assistant)

        print("\n" + "=" * 50)
        print("ALL TESTS PASSED!")
        print("Legal Assistant Agent is working correctly")
        print("\nReady for Demo:")
        print("   1. Run: streamlit run app_simple.py --server.port 8507")
        print("   2. Open: http://localhost:8507")
        print("   3. Click 'Load Sample Contract'")
        print("   4. Ask: 'What is the termination clause?'")

        return True

    except Exception as e:
        print(f"\nTEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)