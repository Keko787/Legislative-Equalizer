"""
Legal Assistant Agent - Simple Streamlit Application
A working version without complex dependencies for immediate testing.
"""

import streamlit as st
import os
from dotenv import load_dotenv
import sys

# Load environment variables
load_dotenv()

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

# Import our modules
from src.utils.document_processor import DocumentProcessor, create_sample_contract
from src.utils.vector_store import VectorStoreManager
from src.memory.conversation_memory import ConversationMemory

# Page configuration
st.set_page_config(
    page_title="Legal Assistant Agent",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
.main-header {
    font-size: 2.5rem;
    font-weight: bold;
    text-align: center;
    margin-bottom: 2rem;
    color: #1e40af;
}

.section-header {
    font-size: 1.5rem;
    font-weight: bold;
    margin-top: 2rem;
    margin-bottom: 1rem;
    color: #374151;
}

.chat-message {
    padding: 1rem;
    border-radius: 0.5rem;
    margin-bottom: 1rem;
}

.user-message {
    background-color: #dbeafe;
    border-left: 4px solid #3b82f6;
}

.assistant-message {
    background-color: #f3f4f6;
    border-left: 4px solid #6b7280;
}
</style>
""", unsafe_allow_html=True)


class SimpleLegalAssistant:
    """Simple Legal Assistant without complex dependencies."""

    def __init__(self):
        self.vector_manager = VectorStoreManager()
        self.memory = ConversationMemory()
        self.document_processed = False
        self.current_document = None

    def process_document(self, uploaded_file=None, use_sample=False):
        """Process document for analysis."""
        try:
            processor = DocumentProcessor()

            if use_sample:
                # Use sample contract
                sample_text = create_sample_contract()
                documents = processor.split_into_chunks(sample_text, "Sample Professional Services Agreement")
                self.current_document = "Sample Professional Services Agreement"
            else:
                # Process uploaded file
                documents = processor.process_pdf(uploaded_file, uploaded_file.name)
                self.current_document = uploaded_file.name

            # Enhance with clause identification
            enhanced_docs = processor.identify_clauses(documents)

            # Add to vector store
            self.vector_manager.create_vectorstore(enhanced_docs)
            self.document_processed = True

            return len(enhanced_docs), True

        except Exception as e:
            st.error(f"Error processing document: {str(e)}")
            return 0, False

    def search_document(self, query: str, num_results: int = 3):
        """Search the document for relevant content."""
        if not self.document_processed:
            return "No document has been processed yet. Please upload a document first."

        try:
            results = self.vector_manager.similarity_search(query, k=num_results)

            if not results:
                return "No relevant information found for your query."

            # Format results
            formatted_results = f"Found {len(results)} relevant sections for: '{query}'\n\n"

            for i, doc in enumerate(results, 1):
                metadata = doc.metadata
                source = metadata.get('source', 'Unknown')
                chunk_id = metadata.get('chunk_id', 'N/A')
                potential_clauses = metadata.get('potential_clauses', [])

                formatted_results += f"📄 **Section {i}**\n"
                formatted_results += f"Source: {source} (Chunk {chunk_id})\n"

                if potential_clauses:
                    formatted_results += f"Identified Clauses: {', '.join(potential_clauses)}\n"

                formatted_results += f"\n**Content:**\n{doc.page_content.strip()}\n\n"
                formatted_results += "---\n\n"

            return formatted_results

        except Exception as e:
            return f"Error searching document: {str(e)}"

    def simple_explain(self, content: str, query: str) -> str:
        """Provide simple explanations without external API."""
        content_lower = content.lower()
        query_lower = query.lower()

        explanation = "**Key Points from the Retrieved Content:**\n\n"

        # Extract key terms and provide simple explanations
        if "termination" in content_lower:
            explanation += "🔚 **Termination**: How and when the agreement can be ended\n"

        if "payment" in content_lower:
            explanation += "💰 **Payment**: Money obligations and payment schedules\n"

        if "liability" in content_lower:
            explanation += "⚖️ **Liability**: Who is responsible if something goes wrong\n"

        if "confidential" in content_lower:
            explanation += "🤐 **Confidentiality**: Rules about keeping information secret\n"

        if "intellectual property" in content_lower or "ip" in content_lower:
            explanation += "🧠 **Intellectual Property**: Rights to ideas, inventions, and creative work\n"

        if "notice" in content_lower:
            explanation += "📢 **Notice**: Requirements for giving formal notification\n"

        if "breach" in content_lower:
            explanation += "❌ **Breach**: Breaking the terms of the agreement\n"

        if "indemnif" in content_lower:
            explanation += "🛡️ **Indemnification**: Protection from legal claims and damages\n"

        explanation += f"\n**Retrieved Content:**\n{content}\n\n"

        explanation += "💡 **What this means in simple terms:**\n"
        explanation += "The above sections contain important legal terms and conditions. "
        explanation += "They define your rights, obligations, and what happens in different situations. "
        explanation += "Review these carefully and consult a lawyer if you need detailed legal advice."

        return explanation

    def process_query(self, query: str) -> str:
        """Process user query and provide response."""
        # Search for relevant content
        search_results = self.search_document(query)

        if "No relevant information" in search_results or "No document has been processed" in search_results:
            # Handle general queries
            return self.handle_general_query(query)

        # For document-specific queries, provide explanation
        explanation = self.simple_explain(search_results, query)

        # Add to memory
        self.memory.add_turn(query, explanation, {"search_results": len(search_results)})

        return explanation

    def handle_general_query(self, query: str) -> str:
        """Handle general queries without document context."""
        query_lower = query.lower()

        if any(greeting in query_lower for greeting in ["hello", "hi", "hey"]):
            return """Hello! I'm your Legal Assistant Agent. 👋

I can help you understand legal documents by:
- 📄 Finding specific clauses and provisions
- 📖 Explaining legal terms in plain English
- 💡 Identifying your rights and obligations
- 🔍 Searching through contract content

To get started:
1. Upload a legal document (PDF) or try the sample contract
2. Ask questions like "What is the termination clause?" or "Explain the payment terms"

How can I help you today?"""

        elif "help" in query_lower:
            return """I can help you understand legal documents! Here's what you can ask me:

**📋 Find Specific Information:**
- "What is the termination clause?"
- "Show me the payment terms"
- "Find the liability section"

**📖 Get Simple Explanations:**
- "Explain this in simple terms"
- "What does liability mean?"
- "What are my obligations?"

**🔍 Search for Topics:**
- "Tell me about confidentiality"
- "What happens if I breach the contract?"
- "Find information about intellectual property"

Upload a document to get started!"""

        else:
            return """I'm here to help you understand legal documents!

To use my services:
1. **Upload a PDF document** using the sidebar
2. **Or try the sample contract** by clicking "Load Sample Contract"
3. **Ask specific questions** about clauses, terms, or provisions

Example questions:
- "What is the termination clause?"
- "Explain the payment terms"
- "What are my rights and obligations?"

What would you like to know about your legal document?"""


def initialize_session_state():
    """Initialize Streamlit session state variables."""
    if "assistant" not in st.session_state:
        st.session_state.assistant = SimpleLegalAssistant()

    if "conversation_history" not in st.session_state:
        st.session_state.conversation_history = []


def display_conversation_history():
    """Display the conversation history."""
    if not st.session_state.conversation_history:
        st.info("💬 Start a conversation by asking questions about your legal document!")
        return

    for turn in st.session_state.conversation_history:
        # User message
        st.markdown(f"""
        <div class="chat-message user-message">
            <strong>You:</strong> {turn['user']}
        </div>
        """, unsafe_allow_html=True)

        # Assistant message
        st.markdown(f"""
        <div class="chat-message assistant-message">
            <strong>Legal Assistant:</strong> {turn['agent']}
        </div>
        """, unsafe_allow_html=True)


def main():
    """Main Streamlit application."""
    initialize_session_state()

    # Header
    st.markdown('<h1 class="main-header">⚖️ Legal Assistant Agent</h1>', unsafe_allow_html=True)
    st.markdown("**Simple RAG System for Legal Document Analysis**")

    # Sidebar
    with st.sidebar:
        st.markdown("### 📋 Document Management")

        # API Key status (simplified)
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            st.success("✅ Ready to assist")
        else:
            st.warning("ℹ️ Running in offline mode")

        st.markdown("---")

        # Document upload section
        st.markdown("#### Upload Legal Document")
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type="pdf",
            help="Upload a legal contract or document for analysis"
        )

        if uploaded_file and uploaded_file != st.session_state.assistant.current_document:
            if st.button("📤 Process Document", type="primary"):
                with st.spinner("🔄 Processing document..."):
                    num_chunks, success = st.session_state.assistant.process_document(uploaded_file)
                    if success:
                        st.success(f"✅ Successfully processed {uploaded_file.name}")
                        st.info(f"📊 Created {num_chunks} document chunks for analysis")

        st.markdown("#### Or Try Sample Document")
        if st.button("📄 Load Sample Contract"):
            with st.spinner("📄 Loading sample contract..."):
                num_chunks, success = st.session_state.assistant.process_document(use_sample=True)
                if success:
                    st.success("✅ Sample contract loaded successfully!")
                    st.info(f"📊 Created {num_chunks} document chunks for analysis")

        st.markdown("---")

        # Document status
        if st.session_state.assistant.document_processed:
            st.success(f"📄 Document: {st.session_state.assistant.current_document}")

            # Vector store stats
            try:
                stats = st.session_state.assistant.vector_manager.get_stats()
                st.markdown(f"📊 **Document Chunks:** {stats.get('total_documents', 0)}")
            except:
                pass
        else:
            st.warning("⚠️ No document loaded")

        st.markdown("---")

        # Clear conversation
        if st.button("🗑️ Clear Conversation"):
            st.session_state.conversation_history = []
            st.session_state.assistant.memory.clear_memory()
            st.rerun()

    # Main content area
    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown('<h2 class="section-header">💬 Chat with Your Document</h2>', unsafe_allow_html=True)

        # Display conversation
        display_conversation_history()

    # User input (outside of columns to avoid streamlit restriction)
    user_query = st.chat_input("Ask me about your legal document...")

    if user_query:
        with st.spinner("🤔 Analyzing your question..."):
            try:
                response = st.session_state.assistant.process_query(user_query)

                # Add to conversation history
                st.session_state.conversation_history.append({
                    "user": user_query,
                    "agent": response
                })

                # Rerun to display new conversation
                st.rerun()

            except Exception as e:
                st.error(f"Error processing query: {str(e)}")

    with col2:
        st.markdown('<h2 class="section-header">💡 Example Questions</h2>', unsafe_allow_html=True)

        if st.session_state.assistant.document_processed:
            example_questions = [
                "What is the termination clause?",
                "What are the payment terms?",
                "Explain the liability terms",
                "What are my obligations?",
                "Tell me about confidentiality",
                "What happens if I breach the contract?",
                "Find information about intellectual property",
                "What notice period is required?"
            ]

            st.markdown("**Click to ask:**")
            for question in example_questions:
                if st.button(question, key=f"example_{hash(question)}"):
                    # Process the example question
                    with st.spinner("🤔 Analyzing..."):
                        response = st.session_state.assistant.process_query(question)
                        st.session_state.conversation_history.append({
                            "user": question,
                            "agent": response
                        })
                        st.rerun()
        else:
            st.info("Upload a document to see example questions!")

        st.markdown("---")

        # About section
        st.markdown("### ℹ️ About")
        st.markdown("""
        This Legal Assistant uses:
        - **Document Processing** for PDF analysis
        - **Vector Search** for finding relevant content
        - **Smart Explanations** for plain English summaries
        - **Memory** for conversation context

        Perfect for understanding legal documents! 📚
        """)


if __name__ == "__main__":
    main()