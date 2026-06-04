"""
Shared state definitions for the multi-agent Legal Assistant system.
All agents read from and write to this shared AgentState.
"""

from typing import Callable, TypedDict, Optional, List, Dict, Any
from dataclasses import dataclass, field


def emit_progress(
    progress: Optional[Callable],
    stage: str,
    message: str,
    fraction: float,
    board: Optional[Dict[str, Any]] = None,
) -> None:
    """Helper for agents to emit progress events. Swallows callback errors.

    board: optional {clause_id: (status, clause_type)} passed in parallel mode
    so the UI can render live per-clause status cards.
    """
    if progress is None:
        return
    try:
        if board is not None:
            try:
                progress(stage, message, max(0.0, min(1.0, float(fraction))), board)
            except TypeError:
                progress(stage, message, max(0.0, min(1.0, float(fraction))))
        else:
            progress(stage, message, max(0.0, min(1.0, float(fraction))))
    except Exception:
        pass


@dataclass
class ClauseBlock:
    """A single identified clause segment from the document."""
    clause_id: str
    clause_type: str          # e.g. "termination", "liability", "payment"
    content: str
    chunk_id: int             # reference back to the vector store chunk


@dataclass
class ClauseAnalysis:
    """Analysis result for a single clause."""
    clause_id: str
    clause_type: str
    risk_level: str           # "low" | "medium" | "high"
    flags: List[str]          # specific risk flags
    obligations: List[str]    # extracted obligations
    plain_summary: str        # student-friendly explanation
    confidence: float = 0.0   # evaluator confidence score (0-1)


@dataclass
class WebResult:
    """A single web research result attached to a clause."""
    url: str
    source_name: str          # e.g. "Indian Kanoon", "BAILII", "Cornell LII"
    title: str
    snippet: str              # extracted main text, truncated to ~600 chars
    retrieved_at: str         # ISO8601 UTC
    relevance: float          # 0-1 cosine similarity to clause text
    tier: int                 # 1 = whitelisted source, 2 = broadened search


@dataclass
class ClauseResearch:
    """Bundled research context for one clause: local retrieval + web results."""
    clause_id: str
    local_context: str                       # text from local vector store
    web_results: List[WebResult] = field(default_factory=list)


class AgentState(TypedDict):
    """Shared state passed between all agents in the DAG."""

    # --- Intake outputs ---
    document_text: str
    document_type: str                    # e.g. "Professional Services Agreement"
    jurisdiction: str                     # "IN" | "UK" | "US" | "EU" | "unknown"
    clause_blocks: List[ClauseBlock]

    # --- Research outputs ---
    research_context: Dict[str, ClauseResearch]   # clause_id → ClauseResearch

    # --- Analysis outputs ---
    analysis_results: List[ClauseAnalysis]

    # --- Evaluator outputs ---
    evaluator_scores: Dict[str, float]            # clause_id → confidence score
    analysis_reflection_count: int                # caps the analysis re-run loop
    research_reflection_count: int                # caps the research re-run loop
    clauses_to_rerun: List[str]                   # clause_ids flagged for re-research
    next_route: str                               # "reflect_research"|"reflect_analysis"|"output"

    # --- Output ---
    final_report: Optional[str]

    # --- Meta ---
    error: Optional[str]
    web_research_enabled: Optional[bool]          # None = use env default; True/False overrides per-run

    # --- Pipeline mode ---
    pipeline_mode: str                             # "sequential" | "parallel"

    # --- Runtime-only (UI handoff) ---
    # LangGraph filters state to declared TypedDict keys at each node
    # boundary, so callbacks must be declared here to propagate.
    _progress: Optional[Callable]                 # progress callback for UI
