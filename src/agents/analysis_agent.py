"""
Analysis Agent — flags risky clauses, extracts obligations, and produces plain summaries.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from ..tools.clause_analyzer_tool import ClauseAnalyzerTool
from .state import AgentState, ClauseBlock, ClauseAnalysis, emit_progress as _emit

log = logging.getLogger(__name__)

SKIP_TYPES = {"miscellaneous"}
MAX_CLAUSES = 20


class AnalysisAgent:
    """Runs the ClauseAnalyzerTool on every clause block that has research context."""

    def __init__(self, api_key: str, model: str = "gpt-5.4"):
        self.analyzer = ClauseAnalyzerTool(api_key=api_key, model=model)

    def run(self, state: AgentState) -> AgentState:
        clause_blocks: List[ClauseBlock] = state.get("clause_blocks", [])
        research_context = state.get("research_context", {})
        progress = state.get("_progress")  # type: ignore[typeddict-item]
        pipeline_mode = state.get("pipeline_mode", "sequential")

        if not clause_blocks:
            state["analysis_results"] = []
            return state

        work_blocks = [b for b in clause_blocks if b.clause_type not in SKIP_TYPES]
        work_blocks = work_blocks[:MAX_CLAUSES]
        total_work = max(1, len(work_blocks))

        _emit(progress, "analysis",
              f"{'⚡ Parallel' if pipeline_mode == 'parallel' else '➡ Sequential'} analysis · "
              f"{total_work} clause{'s' if total_work != 1 else ''}…",
              0.0)

        if pipeline_mode == "parallel":
            results = self._run_parallel(work_blocks, research_context, total_work, progress)
        else:
            results = self._run_sequential(work_blocks, research_context, total_work, progress)

        state["analysis_results"] = results
        return state

    # ── Sequential path ─────────────────────────────────────────────────

    def _run_sequential(
        self,
        work_blocks: List[ClauseBlock],
        research_context: Dict,
        total_work: int,
        progress: Any,
    ) -> List[ClauseAnalysis]:
        results: List[ClauseAnalysis] = []
        for i, block in enumerate(work_blocks):
            _emit(progress, "analysis",
                  f"Analyzing {i + 1}/{total_work} · {block.clause_type}",
                  i / total_work)
            result = self._analyze_clause(block, research_context)
            results.append(result)
            _emit(progress, "analysis",
                  f"Analyzed {i + 1}/{total_work} · {block.clause_type} → {result.risk_level}",
                  (i + 1) / total_work)
        return results

    # ── Parallel path ────────────────────────────────────────────────────

    def _run_parallel(
        self,
        work_blocks: List[ClauseBlock],
        research_context: Dict,
        total_work: int,
        progress: Any,
    ) -> List[ClauseAnalysis]:
        board: Dict[str, Tuple[str, str]] = {
            b.clause_id: ("queued", b.clause_type) for b in work_blocks
        }
        _emit(progress, "analysis",
              f"⚡ Launching {total_work} analysis workers…", 0.0, dict(board))

        results_map: Dict[str, ClauseAnalysis] = {}
        done = 0
        max_workers = min(6, total_work)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._analyze_clause, block, research_context): block
                for block in work_blocks
            }
            for future in as_completed(futures):
                block = futures[future]
                try:
                    result = future.result()
                    results_map[block.clause_id] = result
                    board[block.clause_id] = ("done", block.clause_type)
                    risk = result.risk_level
                except Exception as exc:
                    log.warning("Parallel analysis failed for %s: %s", block.clause_id, exc)
                    results_map[block.clause_id] = ClauseAnalysis(
                        clause_id=block.clause_id,
                        clause_type=block.clause_type,
                        risk_level="medium",
                        flags=[],
                        obligations=[],
                        plain_summary="Could not analyze this clause.",
                        confidence=0.0,
                    )
                    board[block.clause_id] = ("error", block.clause_type)
                    risk = "error"

                done += 1
                _emit(progress, "analysis",
                      f"⚡ {done}/{total_work} done · {block.clause_type} → {risk}",
                      done / total_work, dict(board))

        # Preserve original clause order
        return [results_map[b.clause_id] for b in work_blocks if b.clause_id in results_map]

    # ── Per-clause helper ────────────────────────────────────────────────

    def _analyze_clause(
        self, block: ClauseBlock, research_context: Dict
    ) -> ClauseAnalysis:
        clause_research = research_context.get(block.clause_id)
        context = clause_research.local_context if clause_research else ""
        raw = self.analyzer._run(
            clause_type=block.clause_type,
            content=block.content,
            research_context=context,
        )
        return ClauseAnalysis(
            clause_id=block.clause_id,
            clause_type=block.clause_type,
            risk_level=raw.get("risk_level", "medium"),
            flags=raw.get("flags", []),
            obligations=raw.get("obligations", []),
            plain_summary=raw.get("plain_summary", ""),
            confidence=0.0,
        )
