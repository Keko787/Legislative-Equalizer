"""
Evaluator Agent — scores each clause analysis for confidence and decides
whether to route the DAG back to research, back to analysis, or onward to
output.

Routing policy (Phase 1):
- All clauses meet the confidence threshold → "output"
- Any low-confidence clause classified as "missing_context", and research
  reflection budget remains → "reflect_research" (with clauses_to_rerun set)
- Else, if any low-confidence clause and analysis budget remains
  → "reflect_analysis"
- Else → "output"
"""

import json
from typing import Dict, List, Tuple

from ..tools.evaluator_tool import EvaluatorTool
from .state import AgentState, ClauseAnalysis, ClauseBlock, emit_progress as _emit

CONFIDENCE_THRESHOLD = 0.70   # below this counts as low-confidence
MAX_ANALYSIS_REFLECTIONS = 2
MAX_RESEARCH_REFLECTIONS = 1

# Backward-compat alias — older code paths read MAX_REFLECTIONS.
MAX_REFLECTIONS = MAX_ANALYSIS_REFLECTIONS


class EvaluatorAgent:
    """Scores analysis results and decides the next routing label."""

    def __init__(self, api_key: str, model: str = "gpt-5.4"):
        self.evaluator = EvaluatorTool(api_key=api_key, model=model)

    def run(self, state: AgentState) -> AgentState:
        analysis_results: List[ClauseAnalysis] = state.get("analysis_results", [])
        clause_blocks: List[ClauseBlock] = state.get("clause_blocks", [])
        research_context = state.get("research_context", {}) or {}
        progress = state.get("_progress")  # type: ignore[typeddict-item]

        if not analysis_results:
            state["evaluator_scores"] = {}
            state["next_route"] = "output"
            state["clauses_to_rerun"] = []
            return state

        block_map: Dict[str, ClauseBlock] = {b.clause_id: b for b in clause_blocks}
        scores: Dict[str, float] = {}
        failure_modes: Dict[str, str] = {}

        total = max(1, len(analysis_results))
        _emit(progress, "evaluator",
              f"Scoring {len(analysis_results)} analyses…", 0.0)

        for i, analysis in enumerate(analysis_results):
            _emit(progress, "evaluator",
                  f"Evaluating {i + 1}/{total} · {analysis.clause_type}",
                  i / total)
            block = block_map.get(analysis.clause_id)
            if not block:
                scores[analysis.clause_id] = 0.75
                analysis.confidence = 0.75
                continue

            clause_research = research_context.get(analysis.clause_id)
            context = clause_research.local_context if clause_research else ""
            analysis_json = json.dumps({
                "risk_level":    analysis.risk_level,
                "flags":         analysis.flags,
                "obligations":   analysis.obligations,
                "plain_summary": analysis.plain_summary,
            })

            result = self.evaluator._run(
                clause_type=analysis.clause_type,
                original_content=block.content,
                analysis_json=analysis_json,
                research_context=context,
            )

            score = float(result.get("confidence", 0.5))
            scores[analysis.clause_id] = score
            analysis.confidence = score

            # Capture failure_mode only for low-confidence clauses; tolerate
            # unknown / null values from the tool.
            if score < CONFIDENCE_THRESHOLD:
                fm = result.get("failure_mode")
                if isinstance(fm, str) and fm in ("missing_context", "weak_reasoning"):
                    failure_modes[analysis.clause_id] = fm

        state["evaluator_scores"] = scores
        state["analysis_results"] = analysis_results

        # Decide routing now so should_reflect can just read state.
        route, rerun = self._decide_route(state, scores, failure_modes)
        state["next_route"] = route
        state["clauses_to_rerun"] = rerun
        _emit(progress, "evaluator",
              f"Evaluation complete · next: {route}",
              1.0)
        return state

    @staticmethod
    def _decide_route(
        state: AgentState,
        scores: Dict[str, float],
        failure_modes: Dict[str, str],
    ) -> Tuple[str, List[str]]:
        analysis_count = state.get("analysis_reflection_count", 0)
        research_count = state.get("research_reflection_count", 0)

        low_conf = [cid for cid, s in scores.items() if s < CONFIDENCE_THRESHOLD]
        if not low_conf:
            return "output", []

        # Prefer re-research when missing_context is the dominant cause and
        # the research reflection budget is unspent.
        missing_ctx = [cid for cid in low_conf
                       if failure_modes.get(cid) == "missing_context"]
        if missing_ctx and research_count < MAX_RESEARCH_REFLECTIONS:
            return "reflect_research", missing_ctx

        # Otherwise re-analyze if budget remains.
        if analysis_count < MAX_ANALYSIS_REFLECTIONS:
            return "reflect_analysis", []

        return "output", []

    @staticmethod
    def should_reflect(state: AgentState) -> str:
        """
        Conditional edge function for the DAG. Returns one of:
        "reflect_research" | "reflect_analysis" | "output".
        """
        return state.get("next_route", "output")
