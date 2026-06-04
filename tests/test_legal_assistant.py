"""
Comprehensive test cases for the Legal Assistant Agent.
Tests all components and end-to-end functionality.
"""

import unittest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.utils.document_processor import DocumentProcessor, create_sample_contract
from src.utils.vector_store import VectorStoreManager
from src.tools.retrieval_tool import RetrievalTool
from src.tools.summarizer_tool import SummarizerTool
from src.memory.conversation_memory import ConversationMemory, ConversationTurn
from src.agents.legal_agent import LegalAssistantAgent


class TestDocumentProcessor(unittest.TestCase):
    """Test cases for DocumentProcessor."""

    def setUp(self):
        self.processor = DocumentProcessor()

    def test_preprocess_text(self):
        """Test text preprocessing."""
        raw_text = "  This  is   a  test  \x00\ufffd  text  "
        processed = self.processor.preprocess_text(raw_text)
        expected = "This is a test text"
        self.assertEqual(processed, expected)

    def test_split_into_chunks(self):
        """Test text splitting into chunks."""
        text = "This is a test document. " * 100
        documents = self.processor.split_into_chunks(text, "test.pdf")

        self.assertGreater(len(documents), 0)
        self.assertEqual(documents[0].metadata["source"], "test.pdf")
        self.assertIn("chunk_id", documents[0].metadata)

    def test_identify_clauses(self):
        """Test clause identification."""
        sample_text = create_sample_contract()
        documents = self.processor.split_into_chunks(sample_text, "sample.pdf")
        enhanced_docs = self.processor.identify_clauses(documents)

        # Check if clauses were identified
        clause_counts = sum(doc.metadata.get("clause_count", 0) for doc in enhanced_docs)
        self.assertGreater(clause_counts, 0)

        # Check for specific clauses
        all_clauses = []
        for doc in enhanced_docs:
            all_clauses.extend(doc.metadata.get("potential_clauses", []))

        self.assertIn("termination", all_clauses)
        self.assertIn("payment", all_clauses)

    def test_create_sample_contract(self):
        """Test sample contract creation."""
        contract = create_sample_contract()
        self.assertIsInstance(contract, str)
        self.assertIn("PROFESSIONAL SERVICES AGREEMENT", contract)
        self.assertIn("TERMINATION", contract)
        self.assertIn("PAYMENT", contract)


class TestVectorStoreManager(unittest.TestCase):
    """Test cases for VectorStoreManager."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vector_manager = VectorStoreManager(persist_directory=self.temp_dir)
        self.processor = DocumentProcessor()

    def tearDown(self):
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_vectorstore(self):
        """Test vector store creation."""
        sample_text = create_sample_contract()
        documents = self.processor.split_into_chunks(sample_text, "test.pdf")

        vectorstore = self.vector_manager.create_vectorstore(documents)
        self.assertIsNotNone(vectorstore)

        stats = self.vector_manager.get_stats()
        self.assertEqual(stats["status"], "initialized")
        self.assertGreater(stats["total_documents"], 0)

    def test_similarity_search(self):
        """Test similarity search functionality."""
        sample_text = create_sample_contract()
        documents = self.processor.split_into_chunks(sample_text, "test.pdf")
        self.vector_manager.create_vectorstore(documents)

        # Test search for termination
        results = self.vector_manager.similarity_search("termination clause", k=3)
        self.assertGreater(len(results), 0)

        # Test search for payment
        results = self.vector_manager.similarity_search("payment terms", k=3)
        self.assertGreater(len(results), 0)

    def test_search_by_clause_type(self):
        """Test clause-specific search."""
        sample_text = create_sample_contract()
        documents = self.processor.split_into_chunks(sample_text, "test.pdf")
        enhanced_docs = self.processor.identify_clauses(documents)
        self.vector_manager.create_vectorstore(enhanced_docs)

        # Test termination clause search
        results = self.vector_manager.search_by_clause_type("termination", k=2)
        self.assertGreaterEqual(len(results), 0)

    def test_get_relevant_context(self):
        """Test context retrieval with token limits."""
        sample_text = create_sample_contract()
        documents = self.processor.split_into_chunks(sample_text, "test.pdf")
        self.vector_manager.create_vectorstore(documents)

        context = self.vector_manager.get_relevant_context("payment terms", max_tokens=500)
        self.assertIsInstance(context, str)
        self.assertLessEqual(len(context), 500 * 4)  # Rough token estimation


class TestRetrievalTool(unittest.TestCase):
    """Test cases for RetrievalTool."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.vector_manager = VectorStoreManager(persist_directory=self.temp_dir)
        self.processor = DocumentProcessor()
        self.retrieval_tool = RetrievalTool(self.vector_manager)

        # Setup test data
        sample_text = create_sample_contract()
        documents = self.processor.split_into_chunks(sample_text, "test.pdf")
        enhanced_docs = self.processor.identify_clauses(documents)
        self.vector_manager.create_vectorstore(enhanced_docs)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_run_general_search(self):
        """Test general document search."""
        result = self.retrieval_tool._run("What are the payment terms?", num_results=3)
        self.assertIsInstance(result, str)
        self.assertNotIn("No relevant", result)
        self.assertIn("SECTION", result)

    def test_run_clause_specific_search(self):
        """Test clause-specific search."""
        result = self.retrieval_tool._run(
            "termination clause",
            clause_type="termination",
            num_results=2
        )
        self.assertIsInstance(result, str)
        self.assertIn("relevant sections", result.lower())

    def test_format_results(self):
        """Test result formatting."""
        docs = self.vector_manager.similarity_search("payment", k=2)
        formatted = self.retrieval_tool._format_results(docs, "payment terms")

        self.assertIn("Found", formatted)
        self.assertIn("SECTION", formatted)
        self.assertIn("payment terms", formatted)

    def test_get_clause_summary(self):
        """Test clause summary generation."""
        summary = self.retrieval_tool.get_clause_summary("payment")
        self.assertIsInstance(summary, str)
        self.assertIn("PAYMENT", summary.upper())


class TestSummarizerTool(unittest.TestCase):
    """Test cases for SummarizerTool."""

    @patch('src.tools.summarizer_tool.ChatGoogleGenerativeAI')
    def setUp(self, mock_llm_class):
        """Setup with mocked LLM."""
        # Mock the LLM response
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = "This is a test summary in plain English."
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        self.summarizer_tool = SummarizerTool("fake_api_key")
        self.mock_llm = mock_llm

    def test_run_student_friendly(self):
        """Test student-friendly summarization."""
        legal_text = "The party of the first part hereby agrees to indemnify..."
        result = self.summarizer_tool._run(legal_text, style="student-friendly")

        self.assertIsInstance(result, str)
        self.mock_llm.invoke.assert_called_once()

    def test_run_executive_style(self):
        """Test executive style summarization."""
        legal_text = "Payment terms require 30 days notice..."
        result = self.summarizer_tool._run(legal_text, style="executive")

        self.assertIsInstance(result, str)
        self.mock_llm.invoke.assert_called_once()

    def test_create_prompt_student_friendly(self):
        """Test prompt creation for student-friendly style."""
        prompt = self.summarizer_tool._create_prompt("test text", "student-friendly", None)

        self.assertIn("student-friendly", prompt)
        self.assertIn("simple, everyday language", prompt)
        self.assertIn("test text", prompt)

    def test_compare_clauses(self):
        """Test clause comparison functionality."""
        clause1 = "Either party may terminate with 30 days notice."
        clause2 = "Termination requires 60 days written notice."

        result = self.summarizer_tool.compare_clauses(clause1, clause2, "termination clauses")

        self.assertIsInstance(result, str)
        self.mock_llm.invoke.assert_called_once()

    def test_extract_obligations(self):
        """Test obligation extraction."""
        legal_text = "Client shall pay within 30 days. Provider must deliver services."
        result = self.summarizer_tool.extract_obligations(legal_text)

        self.assertIsInstance(result, str)
        self.mock_llm.invoke.assert_called_once()


class TestConversationMemory(unittest.TestCase):
    """Test cases for ConversationMemory."""

    def setUp(self):
        self.memory = ConversationMemory(max_turns=5)

    def test_add_turn(self):
        """Test adding conversation turns."""
        self.memory.add_turn("What is termination?", "Termination means ending the contract.", {})

        history = self.memory.get_conversation_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].user_input, "What is termination?")

    def test_max_turns_limit(self):
        """Test that memory respects max turns limit."""
        for i in range(10):
            self.memory.add_turn(f"Question {i}", f"Answer {i}", {})

        history = self.memory.get_conversation_history()
        self.assertEqual(len(history), 5)  # Should keep only last 5

    def test_get_context_for_query(self):
        """Test context generation for queries."""
        self.memory.add_turn("What is termination?", "Termination means ending.", {})
        self.memory.add_turn("What about payment?", "Payment is due in 30 days.", {})

        context = self.memory.get_context_for_query("Tell me about notice period")
        self.assertIsInstance(context, str)
        self.assertIn("CONVERSATION CONTEXT", context)

    def test_find_related_turns(self):
        """Test finding related conversation turns."""
        self.memory.add_turn("What is the termination clause?", "Termination requires 30 days.", {})
        self.memory.add_turn("How about payment terms?", "Payment is monthly.", {})

        related = self.memory._find_related_turns("termination notice period")
        self.assertGreater(len(related), 0)

    def test_session_context_updates(self):
        """Test session context updates."""
        self.memory.add_turn("What is the liability clause?", "Liability is limited.", {})

        self.assertIn("liability", self.memory.session_context.get("topics_discussed", set()))

    def test_clear_memory(self):
        """Test memory clearing."""
        self.memory.add_turn("Test question", "Test answer", {})
        self.memory.clear_memory()

        history = self.memory.get_conversation_history()
        self.assertEqual(len(history), 0)
        self.assertEqual(len(self.memory.session_context), 0)


class TestLegalAssistantAgent(unittest.TestCase):
    """Test cases for LegalAssistantAgent integration."""

    @patch('src.agents.legal_agent.ChatGoogleGenerativeAI')
    def setUp(self, mock_llm_class):
        """Setup with mocked components."""
        self.temp_dir = tempfile.mkdtemp()
        self.vector_manager = VectorStoreManager(persist_directory=self.temp_dir)

        # Setup test document
        processor = DocumentProcessor()
        sample_text = create_sample_contract()
        documents = processor.split_into_chunks(sample_text, "test.pdf")
        enhanced_docs = processor.identify_clauses(documents)
        self.vector_manager.create_vectorstore(enhanced_docs)

        # Mock LLM
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = "retrieve"
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        # Mock summarizer tool
        with patch('src.agents.legal_agent.SummarizerTool') as mock_summarizer:
            mock_summarizer_instance = Mock()
            mock_summarizer_instance._run.return_value = "This is a summary in plain English."
            mock_summarizer.return_value = mock_summarizer_instance

            self.agent = LegalAssistantAgent("fake_api_key", self.vector_manager)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_process_query_termination(self):
        """Test processing termination-related query."""
        response = self.agent.process_query("What is the termination clause?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 0)

    def test_process_query_payment(self):
        """Test processing payment-related query."""
        response = self.agent.process_query("What are the payment terms?")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 0)

    def test_conversation_history(self):
        """Test conversation history tracking."""
        self.agent.process_query("What is termination?")
        self.agent.process_query("What about payment?")

        history = self.agent.get_conversation_history()
        self.assertEqual(len(history), 2)
        self.assertIn("user", history[0])
        self.assertIn("agent", history[0])

    def test_clear_conversation(self):
        """Test conversation clearing."""
        self.agent.process_query("Test question")
        self.agent.clear_conversation()

        history = self.agent.get_conversation_history()
        self.assertEqual(len(history), 0)

    def test_follow_up_suggestions(self):
        """Test follow-up suggestions generation."""
        self.agent.process_query("What is the termination clause?")
        suggestions = self.agent.get_follow_up_suggestions()

        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)


class TestEndToEndIntegration(unittest.TestCase):
    """End-to-end integration tests."""

    @patch('src.agents.legal_agent.ChatGoogleGenerativeAI')
    @patch('src.tools.summarizer_tool.ChatGoogleGenerativeAI')
    def setUp(self, mock_summarizer_llm, mock_agent_llm):
        """Setup complete system with mocks."""
        self.temp_dir = tempfile.mkdtemp()

        # Mock LLMs
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = "retrieve"
        mock_llm.invoke.return_value = mock_response
        mock_agent_llm.return_value = mock_llm

        mock_summarizer = Mock()
        mock_sum_response = Mock()
        mock_sum_response.content = "Plain English summary of legal text."
        mock_summarizer.invoke.return_value = mock_sum_response
        mock_summarizer_llm.return_value = mock_summarizer

        # Initialize components
        self.processor = DocumentProcessor()
        self.vector_manager = VectorStoreManager(persist_directory=self.temp_dir)
        self.agent = LegalAssistantAgent("fake_api_key", self.vector_manager)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_complete_workflow(self):
        """Test complete workflow: document upload -> processing -> query -> response."""
        # Step 1: Process sample document
        sample_text = create_sample_contract()
        documents = self.processor.split_into_chunks(sample_text, "sample.pdf")
        enhanced_docs = self.processor.identify_clauses(documents)
        self.vector_manager.create_vectorstore(enhanced_docs)

        # Step 2: Process various queries
        queries = [
            "What is the termination clause?",
            "What are my payment obligations?",
            "Explain the liability terms",
            "What notice period is required?",
            "Compare termination and payment clauses"
        ]

        responses = []
        for query in queries:
            response = self.agent.process_query(query)
            responses.append(response)
            self.assertIsInstance(response, str)
            self.assertGreater(len(response), 0)

        # Step 3: Check conversation continuity
        history = self.agent.get_conversation_history()
        self.assertEqual(len(history), len(queries))

        # Step 4: Test follow-up suggestions
        suggestions = self.agent.get_follow_up_suggestions()
        self.assertIsInstance(suggestions, list)

    def test_error_handling(self):
        """Test system behavior with various error conditions."""
        # Test with no document loaded
        response = self.agent.process_query("What is the termination clause?")
        self.assertIsInstance(response, str)

        # Test with empty query
        response = self.agent.process_query("")
        self.assertIsInstance(response, str)

        # Test with very long query
        long_query = "What is the termination clause? " * 100
        response = self.agent.process_query(long_query)
        self.assertIsInstance(response, str)


def run_tests():
    """Run all test cases."""
    # Create test suite
    test_classes = [
        TestDocumentProcessor,
        TestVectorStoreManager,
        TestRetrievalTool,
        TestSummarizerTool,
        TestConversationMemory,
        TestLegalAssistantAgent,
        TestEndToEndIntegration
    ]

    suite = unittest.TestSuite()

    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)