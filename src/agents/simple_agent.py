"""
Simplified Legal Assistant Agent without complex dependencies.
Focuses on core functionality with direct tool usage.
"""

from typing import Dict, Any, List, Optional
import os
from ..tools.retrieval_tool import RetrievalTool
from ..tools.summarizer_tool import SummarizerTool
from ..memory.conversation_memory import ConversationMemory
from ..utils.vector_store import VectorStoreManager


class SimpleLegalAgent:
    """Simplified Legal Assistant Agent with direct tool usage."""

    def __init__(self, google_api_key: str, vector_store_manager: VectorStoreManager):
        """Initialize the Simple Legal Agent.

        Args:
            google_api_key: Google API key for Gemini
            vector_store_manager: Vector store manager instance
        """
        self.google_api_key = google_api_key
        self.vector_store_manager = vector_store_manager
        self.memory = ConversationMemory()

        # Initialize tools
        self.retrieval_tool = RetrievalTool(vector_store_manager)
        self.summarizer_tool = SummarizerTool(google_api_key)

    def process_query(self, user_query: str) -> str:
        """Process a user query and return a response.

        Args:
            user_query: User's question or request

        Returns:
            Agent's response
        """
        try:
            # Get conversation context
            conversation_context = self.memory.get_context_for_query(user_query)

            # Decide what action to take based on query
            action = self._decide_action(user_query)

            if action == "retrieve_and_summarize":
                # First retrieve relevant content
                retrieved_content = self._retrieve_content(user_query)

                if retrieved_content and "No relevant" not in retrieved_content:
                    # Then summarize it
                    response = self._summarize_content(retrieved_content, user_query)
                else:
                    response = "I couldn't find relevant information about that topic in the loaded document. Please make sure you've uploaded a document or try asking about different topics."

            elif action == "retrieve_only":
                response = self._retrieve_content(user_query)

            elif action == "general_help":
                response = self._generate_general_response(user_query)

            else:
                response = "I'm here to help you understand legal documents. Please upload a document first, then ask questions about specific clauses, terms, or provisions."

            # Add to memory
            self.memory.add_turn(
                user_input=user_query,
                agent_response=response,
                context={"action_taken": action}
            )

            return response

        except Exception as e:
            error_response = f"I apologize, but I encountered an error processing your query: {str(e)}"
            self.memory.add_turn(user_query, error_response, {"error": str(e)})
            return error_response

    def _decide_action(self, query: str) -> str:
        """Decide what action to take based on the query."""
        query_lower = query.lower()
        
        # Get conversation context to check if this is a follow-up
        conversation_context = self.memory.get_context_for_query(query)
        has_context = conversation_context and "No previous conversation context" not in conversation_context

        # Check if this is asking for simplified explanation
        if any(word in query_lower for word in ["explain", "simple", "plain english", "what does", "mean"]):
            return "retrieve_and_summarize"

        # Check if asking for specific legal information
        legal_keywords = [
            "clause", "provision", "term", "agreement", "contract",
            "liability", "termination", "payment", "confidentiality",
            "intellectual property", "notice", "breach", "risk", "obligation"
        ]

        if any(keyword in query_lower for keyword in legal_keywords):
            return "retrieve_and_summarize"

        # Check if asking for comparison
        if any(word in query_lower for word in ["compare", "difference", "vs", "versus"]):
            return "retrieve_and_summarize"

        # Check if this is a document-specific question
        if any(word in query_lower for word in ["document", "contract", "agreement", "this"]):
            return "retrieve_only"

        # Check if this is a follow-up question with context
        if has_context and any(word in query_lower for word in ["what about", "how about", "also", "additionally", "furthermore", "moreover", "explain", "simple", "plain english", "risks", "notice period", "notice"]):
            return "general_help"  # Use context to answer

        # General help or greeting
        return "general_help"

    def _retrieve_content(self, query: str) -> str:
        """Retrieve relevant content from the document."""
        # Determine clause type if applicable
        clause_keywords = {
            "termination": ["termination", "terminate", "end contract"],
            "payment": ["payment", "pay", "fees", "invoice", "money"],
            "liability": ["liability", "liable", "responsibility", "damages"],
            "confidentiality": ["confidential", "non-disclosure", "nda", "secret"],
            "notice": ["notice", "notification", "inform", "notify"],
            "intellectual property": ["ip", "intellectual property", "copyright", "patent"],
            "force majeure": ["force majeure", "act of god", "natural disaster"],
            "governing law": ["governing law", "jurisdiction", "court"]
        }

        clause_type = None
        query_lower = query.lower()

        for clause, keywords in clause_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                clause_type = clause
                break

        # Use the retrieval tool
        if clause_type:
            return self.retrieval_tool._run(
                query=query,
                clause_type=clause_type,
                num_results=5
            )
        else:
            return self.retrieval_tool._run(query=query, num_results=5)

    def _summarize_content(self, content: str, query: str) -> str:
        """Summarize content based on the query."""
        # Determine summarization style
        style = "student-friendly"  # Default
        query_lower = query.lower()

        if "executive" in query_lower or "business" in query_lower:
            style = "executive"
        elif "bullet" in query_lower or "points" in query_lower:
            style = "bullet-points"

        # Determine focus
        focus = None
        if "risk" in query_lower:
            focus = "risks"
        elif "obligation" in query_lower:
            focus = "obligations"
        elif "deadline" in query_lower:
            focus = "deadlines"

        return self.summarizer_tool._run(
            text=content,
            style=style,
            focus=focus
        )

    def _generate_general_response(self, query: str) -> str:
        """Generate a general response for queries not requiring document retrieval."""
        query_lower = query.lower()
        
        # Get conversation context
        conversation_context = self.memory.get_context_for_query(query)

        if any(greeting in query_lower for greeting in ["hello", "hi", "hey"]):
            return """Hello! I'm your Legal Assistant Agent. I can help you understand legal documents by:

📄 **Analyzing uploaded contracts and agreements**
🔍 **Finding specific clauses and provisions**
📖 **Explaining legal terms in plain English**
💡 **Comparing different contract sections**
⚖️ **Identifying your rights and obligations**

To get started, upload a legal document using the sidebar, or try the sample contract. Then ask me questions like:
- "What is the termination clause?"
- "Explain the payment terms in simple language"
- "What are my obligations under this contract?"

How can I help you today?"""

        elif "help" in query_lower:
            return """I can help you understand legal documents! Here's what I can do:

🔍 **Find Information**: Ask about specific clauses, terms, or provisions
📖 **Explain Simply**: Convert legal jargon into plain English
⚖️ **Analyze Risks**: Identify potential risks and obligations
🔄 **Compare Sections**: Compare different parts of your contract
💬 **Remember Context**: I remember our conversation for follow-up questions

**Example Questions:**
- "What does the liability clause mean?"
- "Compare termination vs notice requirements"
- "What happens if I breach this contract?"
- "Explain this in simple terms"

Upload a document to get started, or use the sample contract provided!"""

        else:
            # Check if this is a follow-up question with conversation context
            if conversation_context and "No previous conversation context" not in conversation_context:
                # Provide a more helpful response using the context
                if "explain" in query_lower or "simple" in query_lower or "plain english" in query_lower:
                    return f"""Based on our previous conversation, let me explain this in simpler terms:

{conversation_context}

This means that the contract we discussed earlier contains important information that affects your rights and obligations. The key points are clearly outlined above, and I'm here to help clarify any specific aspects you'd like to understand better."""
                
                elif "risk" in query_lower:
                    return f"""Based on our previous conversation, here are the key risks you should be aware of:

{conversation_context}

These are the main areas where you need to be careful and understand your responsibilities. If you have any specific concerns about these risks, feel free to ask for more details."""
                
                elif "notice" in query_lower:
                    return f"""Based on our previous conversation, here's what you need to know about notice periods:

{conversation_context}

The notice requirements are important to follow to avoid any issues with the contract. Make sure you understand the timing and method of giving notice."""
                
                else:
                    return f"""Based on our previous conversation, I can help you with that question. 

{conversation_context}

Could you please rephrase your question or ask for more specific information about the legal document we've been discussing? I'm here to help clarify any aspects of the contract or legal terms we've covered."""
            else:
                return """I'm your Legal Assistant Agent, designed to help you understand legal documents.

To use my capabilities:
1. **Upload a legal document** (PDF) using the sidebar
2. **Or try the sample contract** by clicking "Load Sample Contract"
3. **Ask specific questions** about clauses, terms, or provisions

I can explain complex legal language in simple terms, find specific information, and help you understand your rights and obligations.

What would you like to know about your legal document?"""

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history for display."""
        turns = self.memory.get_conversation_history()
        return [
            {
                "user": turn.user_input,
                "agent": turn.agent_response,
                "timestamp": turn.timestamp.isoformat()
            }
            for turn in turns
        ]

    def clear_conversation(self) -> None:
        """Clear conversation memory."""
        self.memory.clear_memory()

    def get_follow_up_suggestions(self) -> List[str]:
        """Get suggested follow-up questions."""
        context = self.memory.get_follow_up_context()
        topics = context.get("topics_discussed", [])

        suggestions = [
            "Can you explain this in simpler terms?",
            "What are the key risks I should be aware of?",
            "What are my obligations under this clause?"
        ]

        # Add topic-specific suggestions
        if "termination" in topics:
            suggestions.append("What notice period is required for termination?")
        if "payment" in topics:
            suggestions.append("What happens if payment is late?")
        if "liability" in topics:
            suggestions.append("How much liability am I exposed to?")
        if "confidentiality" in topics:
            suggestions.append("How long does the confidentiality obligation last?")

        return suggestions[:5]  # Return top 5 suggestions