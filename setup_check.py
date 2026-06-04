#!/usr/bin/env python3
"""
Setup verification script for Legal Assistant Agent.
Checks if all components can be imported and initialized.
"""

import sys
import os
import tempfile

def check_imports():
    """Check if all required modules can be imported."""
    print("[*] Checking imports...")

    try:
        # Core dependencies
        import streamlit
        import langchain
        import langgraph
        import faiss
        import google.generativeai as genai
        from sentence_transformers import SentenceTransformer
        import pypdf
        import numpy
        import pandas
        from dotenv import load_dotenv

        print("[✓] All core dependencies imported successfully")

        # Our custom modules
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

        from src.utils.document_processor import DocumentProcessor, create_sample_contract
        from src.utils.vector_store import VectorStoreManager
        from src.tools.retrieval_tool import RetrievalTool
        from src.tools.summarizer_tool import SummarizerTool
        from src.memory.conversation_memory import ConversationMemory
        from src.agents.legal_agent import LegalAssistantAgent

        print("[✓] All custom modules imported successfully")
        return True

    except ImportError as e:
        print(f"[✗] Import error: {e}")
        return False

def test_basic_functionality():
    """Test basic functionality of core components."""
    print("\n[*] Testing basic functionality...")

    try:
        # Test document processing
        print("  [*] Testing document processor...")
        processor = DocumentProcessor()
        sample_text = create_sample_contract()
        documents = processor.split_into_chunks(sample_text, "test.pdf")
        enhanced_docs = processor.identify_clauses(documents)
        print(f"    Created {len(enhanced_docs)} document chunks")

        # Test vector store
        print("  [*] Testing vector store...")
        temp_dir = tempfile.mkdtemp()
        vector_manager = VectorStoreManager(persist_directory=temp_dir)
        vectorstore = vector_manager.create_vectorstore(enhanced_docs)
        print(f"    Vector store created with {len(enhanced_docs)} documents")

        # Test retrieval
        print("  [*] Testing retrieval...")
        retrieval_tool = RetrievalTool(vector_manager)
        results = vector_manager.similarity_search("termination clause", k=2)
        print(f"    Retrieved {len(results)} relevant documents")

        # Test memory
        print("  [*] Testing conversation memory...")
        memory = ConversationMemory()
        memory.add_turn("Test question", "Test answer", {})
        history = memory.get_conversation_history()
        print(f"    Memory working with {len(history)} turns")

        print("[✓] All basic functionality tests passed!")
        return True

    except Exception as e:
        print(f"[✗] Functionality test error: {e}")
        return False

def check_env_setup():
    """Check environment setup."""
    print("\n[*] Checking environment setup...")

    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")

    if api_key:
        print("[✓] Google API Key found")
        if api_key.startswith("AIza"):
            print("[✓] API Key format looks correct")
        else:
            print("[!] API Key format may be incorrect")
        return True
    else:
        print("[✗] Google API Key not found in environment")
        print("   Please set GOOGLE_API_KEY in your .env file")
        return False

def main():
    """Main setup check function."""
    print("Legal Assistant Agent - Setup Verification")
    print("=" * 50)

    success = True

    # Check imports
    success &= check_imports()

    # Test basic functionality
    success &= test_basic_functionality()

    # Check environment
    success &= check_env_setup()

    print("\n" + "=" * 50)
    if success:
        print("Setup verification completed successfully!")
        print("You can now run: streamlit run app.py")
    else:
        print("Setup verification failed!")
        print("Please fix the issues above before running the application.")

    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)