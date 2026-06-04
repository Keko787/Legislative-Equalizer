"""
Conversation memory management for the Legal Assistant Agent.
Handles context retention and conversation history for better follow-up questions.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json


class ConversationTurn:
    """Represents a single turn in the conversation."""

    def __init__(self, user_input: str, agent_response: str, context: Dict[str, Any] = None):
        """Initialize a conversation turn.

        Args:
            user_input: User's question or input
            agent_response: Agent's response
            context: Additional context information
        """
        self.timestamp = datetime.now()
        self.user_input = user_input
        self.agent_response = agent_response
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "user_input": self.user_input,
            "agent_response": self.agent_response,
            "context": self.context
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationTurn':
        """Create from dictionary."""
        turn = cls(data["user_input"], data["agent_response"], data.get("context", {}))
        turn.timestamp = datetime.fromisoformat(data["timestamp"])
        return turn


class ConversationMemory:
    """Manages conversation history and context for the Legal Assistant Agent."""

    def __init__(self, max_turns: int = 20, max_context_tokens: int = 4000):
        """Initialize the conversation memory.

        Args:
            max_turns: Maximum number of conversation turns to remember
            max_context_tokens: Maximum tokens to include in context
        """
        self.max_turns = max_turns
        self.max_context_tokens = max_context_tokens
        self.turns: List[ConversationTurn] = []
        self.session_context: Dict[str, Any] = {}

        # Document-level context set by the Planner after analysis
        self._document_type: str = ""
        self._document_analysis_summary: str = ""

    def set_document_context(self, document_type: str, analysis_results: list) -> None:
        """Store document-level context after the Planner runs the analysis pipeline.

        Args:
            document_type: Identified document type (e.g. "Professional Services Agreement")
            analysis_results: List of ClauseAnalysis dataclass instances
        """
        self._document_type = document_type

        # Build a short summary for use in follow-up prompts
        if analysis_results:
            high   = [r for r in analysis_results if r.risk_level == "high"]
            medium = [r for r in analysis_results if r.risk_level == "medium"]
            low    = [r for r in analysis_results if r.risk_level == "low"]
            lines = [
                f"Document type: {document_type}",
                f"Clauses analyzed: {len(analysis_results)} "
                f"(High: {len(high)}, Medium: {len(medium)}, Low: {len(low)})",
            ]
            if high:
                lines.append("High-risk clause types: " +
                              ", ".join(r.clause_type for r in high))
            self._document_analysis_summary = " | ".join(lines)
        else:
            self._document_analysis_summary = f"Document type: {document_type} — no clauses analyzed"

        self.session_context["document_type"] = document_type
        self.session_context["analysis_complete"] = True

    def get_document_context_summary(self) -> str:
        """Return the stored document analysis summary for use in prompts."""
        return self._document_analysis_summary or "No document analysis available."

    def add_turn(self, user_input: str, agent_response: str, context: Dict[str, Any] = None) -> None:
        """Add a new conversation turn.

        Args:
            user_input: User's question or input
            agent_response: Agent's response
            context: Additional context information
        """
        turn = ConversationTurn(user_input, agent_response, context)
        self.turns.append(turn)

        # Keep only the most recent turns
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]

        # Update session context with relevant information
        self._update_session_context(turn)

    def get_conversation_history(self, num_turns: Optional[int] = None) -> List[ConversationTurn]:
        """Get recent conversation history.

        Args:
            num_turns: Number of recent turns to retrieve (default: all)

        Returns:
            List of recent conversation turns
        """
        if num_turns is None:
            return self.turns.copy()
        return self.turns[-num_turns:] if self.turns else []

    def get_context_for_query(self, current_query: str) -> str:
        """Get relevant context for the current query.

        Args:
            current_query: Current user query

        Returns:
            Formatted context string
        """
        if not self.turns:
            return "No previous conversation context."

        context_parts = ["CONVERSATION CONTEXT:"]

        # Add session context if available
        if self.session_context:
            context_parts.append("\nSession Information:")
            for key, value in self.session_context.items():
                context_parts.append(f"- {key}: {value}")

        # Add recent conversation turns
        recent_turns = self.get_conversation_history(5)  # Last 5 turns
        if recent_turns:
            context_parts.append("\nRecent Conversation:")
            for i, turn in enumerate(recent_turns, 1):
                context_parts.append(f"\n{i}. User: {turn.user_input}")
                # Truncate long responses
                response = turn.agent_response[:200] + "..." if len(turn.agent_response) > 200 else turn.agent_response
                context_parts.append(f"   Agent: {response}")

        # Check for relevant previous queries
        related_turns = self._find_related_turns(current_query)
        if related_turns:
            context_parts.append("\nRelated Previous Queries:")
            for turn in related_turns:
                context_parts.append(f"- User asked: {turn.user_input}")

        context_text = "\n".join(context_parts)

        # Trim if too long
        if len(context_text) * 4 > self.max_context_tokens:  # Rough token estimation
            # Keep only the most recent parts
            parts_to_keep = context_parts[:3] + context_parts[-3:]
            context_text = "\n".join(parts_to_keep)

        return context_text

    def _update_session_context(self, turn: ConversationTurn) -> None:
        """Update session context based on the conversation turn.

        Args:
            turn: New conversation turn
        """
        # Track topics discussed
        topics = self.session_context.get("topics_discussed", set())

        # Identify legal topics from the conversation
        legal_keywords = [
            "termination", "liability", "payment", "confidentiality",
            "indemnification", "intellectual property", "force majeure",
            "governing law", "notice", "breach", "damages", "warranty"
        ]

        user_lower = turn.user_input.lower()
        for keyword in legal_keywords:
            if keyword in user_lower:
                topics.add(keyword)

        self.session_context["topics_discussed"] = topics

        # Track document-related context
        if "document" in user_lower or "contract" in user_lower:
            self.session_context["document_queries"] = self.session_context.get("document_queries", 0) + 1

        # Track clause-related queries
        if "clause" in user_lower:
            self.session_context["clause_queries"] = self.session_context.get("clause_queries", 0) + 1

        # Update last query timestamp
        self.session_context["last_query_time"] = turn.timestamp.isoformat()

    def _find_related_turns(self, current_query: str, similarity_threshold: int = 3) -> List[ConversationTurn]:
        """Find previous turns related to the current query.

        Args:
            current_query: Current user query
            similarity_threshold: Minimum number of common words for similarity

        Returns:
            List of related conversation turns
        """
        if not self.turns:
            return []

        current_words = set(current_query.lower().split())
        related_turns = []

        for turn in self.turns[-10:]:  # Check last 10 turns
            turn_words = set(turn.user_input.lower().split())
            common_words = current_words.intersection(turn_words)

            if len(common_words) >= similarity_threshold:
                related_turns.append(turn)

        return related_turns

    def get_follow_up_context(self) -> Dict[str, Any]:
        """Get context useful for generating follow-up questions.

        Returns:
            Dictionary with follow-up context
        """
        if not self.turns:
            return {}

        last_turn = self.turns[-1]
        context = {
            "last_query": last_turn.user_input,
            "last_response_summary": last_turn.agent_response[:100] + "...",
            "topics_discussed": list(self.session_context.get("topics_discussed", [])),
            "conversation_length": len(self.turns)
        }

        # Suggest potential follow-up areas
        suggested_followups = []
        if "topics_discussed" in self.session_context:
            topics = self.session_context["topics_discussed"]
            if "termination" in topics and "notice" not in topics:
                suggested_followups.append("notice requirements for termination")
            if "liability" in topics and "damages" not in topics:
                suggested_followups.append("types of damages mentioned")

        context["suggested_followups"] = suggested_followups
        return context

    def clear_memory(self) -> None:
        """Clear all conversation memory."""
        self.turns.clear()
        self.session_context.clear()

    def export_conversation(self) -> Dict[str, Any]:
        """Export conversation history for persistence.

        Returns:
            Dictionary containing conversation data
        """
        return {
            "turns": [turn.to_dict() for turn in self.turns],
            "session_context": self.session_context,
            "export_timestamp": datetime.now().isoformat()
        }

    def import_conversation(self, data: Dict[str, Any]) -> None:
        """Import conversation history from exported data.

        Args:
            data: Exported conversation data
        """
        self.turns = [ConversationTurn.from_dict(turn_data) for turn_data in data.get("turns", [])]
        self.session_context = data.get("session_context", {})

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get statistics about the current memory state.

        Returns:
            Dictionary with memory statistics
        """
        return {
            "total_turns": len(self.turns),
            "topics_discussed": len(self.session_context.get("topics_discussed", [])),
            "session_start": self.turns[0].timestamp.isoformat() if self.turns else None,
            "last_activity": self.turns[-1].timestamp.isoformat() if self.turns else None,
            "memory_usage": f"{len(self.turns)}/{self.max_turns} turns"
        }