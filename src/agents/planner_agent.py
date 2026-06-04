"""
Planner Agent — orchestrates all specialized agents in a LangGraph DAG.

DAG flow:
    intake → research → analysis → evaluator → (reflect_research → research
                                              |  reflect_analysis → analysis
                                              |  output)

Two reflection counters are tracked separately and capped to prevent
infinite cycles:
- analysis_reflection_count, capped at EvaluatorAgent.MAX_ANALYSIS_REFLECTIONS
- research_reflection_count, capped at EvaluatorAgent.MAX_RESEARCH_REFLECTIONS
"""

from typing import Callable, Dict, Any, List, Optional
from langgraph.graph import StateGraph, END

# Progress callback signature: (stage, message, intra_stage_fraction).
# stage ∈ {"intake","research","analysis","evaluator","output"}.
# intra_stage_fraction ∈ [0.0, 1.0] — progress within the current stage.
ProgressCallback = Callable[[str, str, float], None]

from .state import AgentState
from .intake_agent import IntakeAgent
from .research_agent import ResearchAgent
from .analysis_agent import AnalysisAgent
from .evaluator_agent import EvaluatorAgent
from .output_agent import OutputAgent
from ..utils.vector_store import VectorStoreManager
from ..memory.conversation_memory import ConversationMemory


class PlannerAgent:
    """
    Top-level orchestrator.  Exposes two public methods:

    - analyze_document(text)  → runs the full DAG and returns the report string
    - process_query(query)    → conversational follow-up using memory
    """

    def __init__(
        self,
        api_key: str,
        vector_store_manager: VectorStoreManager,
        openai_model: str = "gpt-4o-mini",
    ):
        self.api_key = api_key
        self.vector_store_manager = vector_store_manager
        self.model = openai_model
        self.memory = ConversationMemory()

        # Instantiate all agents
        self._intake    = IntakeAgent(api_key, openai_model)
        self._research  = ResearchAgent(vector_store_manager, api_key=api_key, model=openai_model)
        self._analysis  = AnalysisAgent(api_key, openai_model)
        self._evaluator = EvaluatorAgent(api_key, openai_model)
        self._output    = OutputAgent(api_key, openai_model)

        # Compile the DAG once
        self._graph = self._build_graph()

        # Cache the last report for follow-up context
        self._last_report: Optional[str] = None
        self._document_type: Optional[str] = None
        # Cache the full final state for debugging / introspection
        self._last_state: Optional[AgentState] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_document(
        self,
        document_text: str,
        web_research_enabled: Optional[bool] = None,
        progress: Optional[ProgressCallback] = None,
        pipeline_mode: str = "sequential",
    ) -> str:
        """
        Run the full multi-agent pipeline on a document.

        Args:
            document_text: raw text of the document.
            web_research_enabled: per-run override for the web research
                sub-agent. None defers to WEB_RESEARCH_ENABLED env var.
            progress: optional callback `(stage, message, fraction)` invoked
                throughout the pipeline so the UI can render real-time
                progress instead of fake checkpoints.

        Returns the final markdown report string.
        """
        initial_state: AgentState = {
            "document_text":              document_text,
            "document_type":              "",
            "jurisdiction":               "unknown",
            "clause_blocks":              [],
            "research_context":           {},
            "analysis_results":           [],
            "evaluator_scores":           {},
            "analysis_reflection_count":  0,
            "research_reflection_count":  0,
            "clauses_to_rerun":           [],
            "next_route":                 "output",
            "final_report":               None,
            "error":                      None,
            "web_research_enabled":       web_research_enabled,
            "pipeline_mode":              pipeline_mode,
            "_progress":                  progress,
        }

        try:
            final_state = self._graph.invoke(initial_state)
            self._last_state    = final_state
            self._last_report   = final_state.get("final_report", "")
            self._document_type = final_state.get("document_type", "")
            self.memory.set_document_context(
                document_type=self._document_type,
                analysis_results=final_state.get("analysis_results", [])
            )
            return self._last_report or "Analysis complete — no report generated."
        except Exception as e:
            return f"Error during document analysis: {str(e)}"

    def get_last_state(self) -> Optional[AgentState]:
        """Return the last completed pipeline state (for debugging / inspection)."""
        return self._last_state

    def process_query(self, user_query: str) -> str:
        """Handle a conversational follow-up query using memory context."""
        from ..tools.summarizer_tool import SummarizerTool
        from ..tools.retrieval_tool import RetrievalTool
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage

        llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            temperature=0.3
        )

        conversation_context = self.memory.get_context_for_query(user_query)
        doc_context = self.memory.get_document_context_summary()

        # Retrieve relevant chunks from the vector store for the query
        retrieval_tool = RetrievalTool(self.vector_store_manager)
        retrieved = retrieval_tool._run(query=user_query, num_results=4)

        prompt = f"""You are a Legal Assistant Agent helping a non-lawyer understand a legal document.

Document Type: {self._document_type or 'Legal Document'}

Document Analysis Summary:
{doc_context}

Retrieved Document Sections:
{retrieved}

Conversation Context:
{conversation_context}

User Question: "{user_query}"

Answer the user's question clearly and in plain English.
Draw on the retrieved sections and analysis summary above.
Be specific — avoid vague answers. Keep it under 300 words."""

        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            answer = response.content.strip()
        except Exception as e:
            answer = f"I encountered an error processing your question: {str(e)}"

        self.memory.add_turn(
            user_input=user_query,
            agent_response=answer,
            context={"source": "planner_query"}
        )
        return answer

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        turns = self.memory.get_conversation_history()
        return [
            {"user": t.user_input, "agent": t.agent_response,
             "timestamp": t.timestamp.isoformat()}
            for t in turns
        ]

    def clear_conversation(self) -> None:
        self.memory.clear_memory()
        self._last_report = None
        self._document_type = None

    def get_follow_up_suggestions(self) -> List[str]:
        context = self.memory.get_follow_up_context()
        topics = context.get("topics_discussed", [])

        suggestions = [
            "What are the key risks I should know about?",
            "Explain the termination clause in simple terms",
            "What are my obligations under this contract?",
            "Are there any payment penalties?",
            "What happens if either party breaches this agreement?",
        ]
        if "liability" in topics:
            suggestions.insert(0, "How much liability am I exposed to?")
        if "confidentiality" in topics:
            suggestions.insert(0, "How long does the confidentiality obligation last?")

        return suggestions[:5]

    # ------------------------------------------------------------------
    # DAG construction
    # ------------------------------------------------------------------

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        # Register nodes
        workflow.add_node("intake",    self._intake_node)
        workflow.add_node("research",  self._research_node)
        workflow.add_node("analysis",  self._analysis_node)
        workflow.add_node("evaluator", self._evaluator_node)
        workflow.add_node("output",    self._output_node)

        # Linear edges
        workflow.set_entry_point("intake")
        workflow.add_edge("intake",   "research")
        workflow.add_edge("research", "analysis")
        workflow.add_edge("analysis", "evaluator")

        # Conditional edge: reflect (research or analysis) or finish.
        workflow.add_conditional_edges(
            "evaluator",
            EvaluatorAgent.should_reflect,
            {
                "reflect_research": "research",   # re-research flagged clauses
                "reflect_analysis": "analysis",   # re-analyze with same context
                "output":           "output",
            }
        )

        workflow.add_edge("output", END)
        return workflow.compile()

    # ------------------------------------------------------------------
    # Node wrappers (increment analysis_reflection_count before re-analysis)
    # ------------------------------------------------------------------

    def _intake_node(self, state: AgentState) -> AgentState:
        return self._intake.run(state)

    def _research_node(self, state: AgentState) -> AgentState:
        # Increment counter each time research runs (first run = 0 → 1)
        state["research_reflection_count"] = state.get("research_reflection_count", 0) + 1
        return self._research.run(state)

    def _analysis_node(self, state: AgentState) -> AgentState:
        # Increment counter each time analysis runs (first run = 0 → 1)
        state["analysis_reflection_count"] = state.get("analysis_reflection_count", 0) + 1
        return self._analysis.run(state)

    def _evaluator_node(self, state: AgentState) -> AgentState:
        return self._evaluator.run(state)

    def _output_node(self, state: AgentState) -> AgentState:
        return self._output.run(state)
