"""
Legal Assistant Agent using LangGraph with ReAct pattern.
Combines retrieval and summarization tools with conversational memory.
"""

from typing import Dict, Any, List, Optional, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
import json

from ..tools.retrieval_tool import RetrievalTool
from ..tools.summarizer_tool import SummarizerTool
from ..memory.conversation_memory import ConversationMemory
from ..utils.vector_store import VectorStoreManager


class AgentState(TypedDict):
    """State of the Legal Assistant Agent."""
    messages: List[Any]
    user_query: str
    retrieved_content: Optional[str]
    summary: Optional[str]
    conversation_context: Optional[str]
    next_action: Optional[str]
    final_response: Optional[str]


class LegalAssistantAgent:
    """Legal Assistant Agent with ReAct pattern using LangGraph."""

    def __init__(
        self,
        api_key: str,
        vector_store_manager: VectorStoreManager,
        openai_model: str = "gpt-5.4"
    ):
        """Initialize the Legal Assistant Agent.

        Args:
            google_api_key: Google API key for Gemini
            vector_store_manager: Vector store manager instance
            openai_model: Gemini model to use (default: gpt-5.4)
        """
        self.api_key = api_key
        self.vector_store_manager = vector_store_manager
        self.memory = ConversationMemory()

        # Initialize LLM
        self.llm = ChatOpenAI(
            model=openai_model,
            api_key=api_key,
            temperature=0.3
        )

        # Initialize tools
        self.retrieval_tool = RetrievalTool(vector_store_manager)
        self.summarizer_tool = SummarizerTool(api_key, openai_model)

        # Store tools for reference
        self.tools = [self.retrieval_tool, self.summarizer_tool]

        # Build the graph
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("reasoning", self._reasoning_node)
        workflow.add_node("retrieve", self._retrieve_node)
        workflow.add_node("summarize", self._summarize_node)
        workflow.add_node("respond", self._respond_node)

        # Set entry point
        workflow.set_entry_point("reasoning")

        # Add conditional edges
        workflow.add_conditional_edges(
            "reasoning",
            self._should_retrieve_or_summarize,
            {
                "retrieve": "retrieve",
                "summarize": "summarize",
                "respond": "respond"
            }
        )

        workflow.add_edge("retrieve", "summarize")
        workflow.add_edge("summarize", "respond")
        workflow.add_edge("respond", END)

        return workflow.compile()

    def _reasoning_node(self, state: AgentState) -> AgentState:
        """Reasoning node - decides what action to take."""
        user_query = state["user_query"]
        conversation_context = self.memory.get_context_for_query(user_query)

        reasoning_prompt = f"""You are a Legal Assistant Agent helping students understand legal documents.

Conversation Context:
{conversation_context}

Current User Query: "{user_query}"

Based on the query and conversation context, determine what action you need to take:
1. "retrieve" - if the user is asking about specific clauses, document content, or needs NEW information from the document
2. "summarize" - if you already have content that needs to be simplified or explained
3. "respond" - if this is a follow-up question that can be answered using conversation context, or a general question

IMPORTANT: 
- If this is a follow-up question that can be answered using the conversation context, choose "respond"
- If the user is asking for clarification, examples, or building on previous answers, choose "respond"
- If the user is asking about something already discussed in the conversation, choose "respond"
- If the user is asking "What are the key risks" or "notice period" and we have context, choose "respond"

Examples of when to choose "respond":
- "Can you explain this in simpler terms?" (follow-up)
- "What are the key risks?" (follow-up if we have context)
- "notice period" (follow-up if we have context)
- "What about..." (follow-up)

Examples of when to choose "retrieve":
- First time asking about a specific clause
- Asking about new topics not in conversation context

Consider the conversation context to provide better continuity.

Respond with just one word: retrieve, summarize, or respond"""

        try:
            response = self.llm.invoke([HumanMessage(content=reasoning_prompt)])
            next_action = response.content.strip().lower()

            if next_action not in ["retrieve", "summarize", "respond"]:
                next_action = "retrieve"  # Default to retrieve

            state["next_action"] = next_action
            state["conversation_context"] = conversation_context

        except Exception as e:
            state["next_action"] = "retrieve"  # Default action on error

        return state

    def _should_retrieve_or_summarize(self, state: AgentState) -> str:
        """Conditional edge function to determine next node."""
        return state.get("next_action", "retrieve")

    def _retrieve_node(self, state: AgentState) -> AgentState:
        """Retrieval node - retrieves relevant document content."""
        user_query = state["user_query"]

        # Determine if this is a clause-specific query
        clause_keywords = {
            "termination": ["termination", "terminate", "end contract"],
            "payment": ["payment", "pay", "fees", "invoice"],
            "liability": ["liability", "liable", "responsibility"],
            "confidentiality": ["confidential", "non-disclosure", "nda"],
            "notice": ["notice", "notification", "inform"],
            "indemnification": ["indemnify", "indemnification"],
            "intellectual property": ["ip", "intellectual property", "copyright"],
            "force majeure": ["force majeure", "act of god"],
            "governing law": ["governing law", "jurisdiction"]
        }

        clause_type = None
        user_query_lower = user_query.lower()

        for clause, keywords in clause_keywords.items():
            if any(keyword in user_query_lower for keyword in keywords):
                clause_type = clause
                break

        try:
            # Use the retrieval tool
            if clause_type:
                retrieved_content = self.retrieval_tool._run(
                    query=user_query,
                    clause_type=clause_type,
                    num_results=5
                )
            else:
                retrieved_content = self.retrieval_tool._run(
                    query=user_query,
                    num_results=5
                )

            state["retrieved_content"] = retrieved_content

        except Exception as e:
            state["retrieved_content"] = f"Error retrieving content: {str(e)}"

        return state

    def _summarize_node(self, state: AgentState) -> AgentState:
        """Summarization node - simplifies retrieved content."""
        retrieved_content = state.get("retrieved_content", "")
        user_query = state["user_query"]

        if not retrieved_content or "No relevant" in retrieved_content or "Error" in retrieved_content:
            state["summary"] = retrieved_content
            return state

        # Determine summarization style based on query
        style = "student-friendly"  # Default
        if "executive" in user_query.lower() or "business" in user_query.lower():
            style = "executive"
        elif "bullet" in user_query.lower() or "points" in user_query.lower():
            style = "bullet-points"

        # Determine focus
        focus = None
        if "risk" in user_query.lower():
            focus = "risks"
        elif "obligation" in user_query.lower():
            focus = "obligations"
        elif "deadline" in user_query.lower():
            focus = "deadlines"

        try:
            summary = self.summarizer_tool._run(
                text=retrieved_content,
                style=style,
                focus=focus
            )
            state["summary"] = summary

        except Exception as e:
            state["summary"] = f"Error summarizing content: {str(e)}"

        return state

    def _respond_node(self, state: AgentState) -> AgentState:
        """Response node - generates final response."""
        user_query = state["user_query"]
        conversation_context = state.get("conversation_context", "")
        retrieved_content = state.get("retrieved_content", "")
        summary = state.get("summary", "")

        # Build the response based on what we have
        if summary and summary != retrieved_content:
            # We have a summarized version
            final_response = summary
        elif retrieved_content:
            # We have retrieved content but no summary
            final_response = retrieved_content
        else:
            # Generate a direct response
            response_prompt = f"""You are a helpful Legal Assistant Agent for students.

CRITICAL: Generate clean, properly formatted text with correct spacing between all words. Do NOT generate text with missing spaces between words.

Conversation Context:
{conversation_context}

User Query: "{user_query}"

Based on the conversation context and the user's query, provide a helpful response. 
- If this is a follow-up question, build upon the previous conversation
- If this is a general legal question, provide educational information
- If the user is asking about document content, use the conversation context to provide relevant information
- Always maintain conversation continuity and context
- Provide complete, substantive answers - don't just say "What this means in plain English:" without explaining

IMPORTANT: Give a complete answer. Don't just start with "What this means in plain English:" and then stop. Provide the actual explanation.

Keep your response friendly, educational, and appropriate for students learning about legal documents."""

            try:
                response = self.llm.invoke([HumanMessage(content=response_prompt)])
                final_response = self._clean_response(response.content)
            except Exception as e:
                final_response = f"I apologize, but I encountered an error: {str(e)}"

        state["final_response"] = final_response
        return state

    def _clean_response(self, response: str) -> str:
        """Clean and format the LLM response."""
        if not response:
            return response
            
        import re
        
        # Remove unwanted prefixes
        response = re.sub(r'^What this means in plain English:\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'^In plain English:\s*', '', response, flags=re.IGNORECASE)
        
        # Basic text cleaning (stable model shouldn't need aggressive fixes)
        response = re.sub(r'([.!?])([A-Z])', r'\1 \2', response)  # Fix missing spaces after punctuation
        response = re.sub(r'([,])([A-Z])', r'\1 \2', response)    # Fix missing spaces after commas
        response = re.sub(r'(\d+)([A-Z])', r'\1 \2', response)    # Fix missing spaces after numbers
        
        # Fix multiple spaces but preserve line breaks
        response = re.sub(r'[ \t]+', ' ', response)
        response = re.sub(r'\n\s*\n', '\n\n', response)
        
        return response.strip()

    def process_query(self, user_query: str) -> str:
        """Process a user query and return a response.

        Args:
            user_query: User's question or request

        Returns:
            Agent's response
        """
        # Initialize state
        initial_state = {
            "messages": [],
            "user_query": user_query,
            "retrieved_content": None,
            "summary": None,
            "conversation_context": None,
            "next_action": None,
            "final_response": None
        }

        try:
            # Run the graph
            final_state = self.graph.invoke(initial_state)
            response = final_state.get("final_response", "I couldn't process your query.")

            # Add to memory
            self.memory.add_turn(
                user_input=user_query,
                agent_response=response,
                context={
                    "retrieved_content_length": len(final_state.get("retrieved_content", "")),
                    "action_taken": final_state.get("next_action", "unknown")
                }
            )

            return response

        except Exception as e:
            error_response = f"I apologize, but I encountered an error processing your query: {str(e)}"
            self.memory.add_turn(user_query, error_response, {"error": str(e)})
            return error_response

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history for display.

        Returns:
            List of conversation turns
        """
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
        """Get suggested follow-up questions.

        Returns:
            List of suggested questions
        """
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

        return suggestions[:5]  # Return top 5 suggestions