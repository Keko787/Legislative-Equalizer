"""
Research Agent — retrieves legal context for each clause block using RAG,
augmented (when enabled) by the Web Research Sub-Agent.

On a re-research pass triggered by the evaluator, only clauses listed in
state["clauses_to_rerun"] are re-processed; the rest are carried over from
the prior pass. Re-research forces the triage gate open and (in Phase 2)
allows Tier 2 broadened web search.
"""

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..tools.retrieval_tool import RetrievalTool
from ..utils.vector_store import VectorStoreManager
from .state import AgentState, ClauseBlock, ClauseResearch, WebResult, emit_progress as _emit

# Web research modules are optional — if the files don't exist the pipeline
# still runs; web research is simply skipped.
try:
    from ..tools.web_fetch_tool import WebFetchTool
    from ..tools.web_search_tool import WebSearchTool
    from .web_research_subagent import WebResearchSubAgent
    from ._web_constants import HIGH_STAKES_TYPES
    _WEB_AVAILABLE = True
except ImportError:
    WebFetchTool = None          # type: ignore[assignment,misc]
    WebSearchTool = None         # type: ignore[assignment,misc]
    WebResearchSubAgent = None   # type: ignore[assignment,misc]
    HIGH_STAKES_TYPES: set = set()
    _WEB_AVAILABLE = False

log = logging.getLogger(__name__)

# Detects statute / section / article references that warrant web research
# even when the local store has plenty of context.
_STATUTE_RE = re.compile(
    r"\b(?:Section|Sec\.?|§|Article|Art\.?)\s*\d+|\bAct,?\s+\d{4}\b",
    re.IGNORECASE,
)

# Below this length the local retrieval is considered "thin" and triggers web.
_THIN_LOCAL_THRESHOLD = 200


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


class ResearchAgent:
    """Retrieves local + (optional) web context for every clause."""

    def __init__(
        self,
        vector_store_manager: VectorStoreManager,
        api_key: Optional[str] = None,
        model: str = "gpt-5.4",
    ):
        self.retrieval_tool = RetrievalTool(vector_store_manager)
        if _WEB_AVAILABLE:
            self.web_subagent = WebResearchSubAgent(
                search_tool=WebSearchTool(),
                fetch_tool=WebFetchTool(
                    cache_ttl_days=int(_env_float("WEB_RESEARCH_CACHE_TTL_DAYS", 14.0)),
                ),
                api_key=api_key,
                model=model,
                per_clause_timeout=_env_float("WEB_RESEARCH_PER_CLAUSE_TIMEOUT_SEC", 12.0),
            )
        else:
            self.web_subagent = None

    # ── Public entry point ──────────────────────────────────────────────

    def run(self, state: AgentState) -> AgentState:
        clause_blocks: List[ClauseBlock] = state.get("clause_blocks", [])
        jurisdiction = state.get("jurisdiction", "unknown")
        prior_research: Dict[str, ClauseResearch] = state.get("research_context", {}) or {}
        clauses_to_rerun = list(state.get("clauses_to_rerun", []) or [])
        progress = state.get("_progress")  # type: ignore[typeddict-item]
        pipeline_mode = state.get("pipeline_mode", "sequential")

        if not clause_blocks:
            state["research_context"] = {}
            state["clauses_to_rerun"] = []
            return state

        web_enabled = self._web_enabled(state)
        per_doc_budget = _env_float("WEB_RESEARCH_PER_DOC_BUDGET_SEC", 60.0)
        deadline = time.monotonic() + per_doc_budget

        is_rerun = bool(clauses_to_rerun)
        rerun_set = set(clauses_to_rerun)

        work_blocks = [
            b for b in clause_blocks
            if (not is_rerun) or b.clause_id in rerun_set
        ]
        total_work = max(1, len(work_blocks))

        _emit(progress, "research",
              f"{'⚡ Parallel' if pipeline_mode == 'parallel' else '➡ Sequential'} research · "
              f"{total_work} clause{'s' if total_work != 1 else ''}…", 0.0)

        # Carry over prior context for clauses not in this pass's work set.
        new_context: Dict[str, ClauseResearch] = {}
        for block in clause_blocks:
            if is_rerun and block.clause_id not in rerun_set:
                if block.clause_id in prior_research:
                    new_context[block.clause_id] = prior_research[block.clause_id]

        if pipeline_mode == "parallel":
            new_context = self._run_parallel(
                work_blocks, new_context, is_rerun, jurisdiction,
                web_enabled, deadline, total_work, progress,
            )
        else:
            new_context = self._run_sequential(
                work_blocks, new_context, is_rerun, jurisdiction,
                web_enabled, deadline, total_work, progress,
            )

        state["research_context"] = new_context
        state["clauses_to_rerun"] = []
        return state

    # ── Sequential path (original behaviour) ───────────────────────────

    def _run_sequential(
        self,
        work_blocks: List[ClauseBlock],
        new_context: Dict[str, ClauseResearch],
        is_rerun: bool,
        jurisdiction: str,
        web_enabled: bool,
        deadline: float,
        total_work: int,
        progress: Any,
    ) -> Dict[str, ClauseResearch]:
        done = 0
        for block in work_blocks:
            result, triggered_web = self._process_clause(
                block, is_rerun, jurisdiction, web_enabled, deadline,
            )
            new_context[block.clause_id] = result
            done += 1
            verb = "web" if triggered_web else "local"
            _emit(progress, "research",
                  f"Researched {done}/{total_work} · {verb} · {block.clause_type}",
                  done / total_work)
        return new_context

    # ── Parallel path ───────────────────────────────────────────────────

    def _run_parallel(
        self,
        work_blocks: List[ClauseBlock],
        new_context: Dict[str, ClauseResearch],
        is_rerun: bool,
        jurisdiction: str,
        web_enabled: bool,
        deadline: float,
        total_work: int,
        progress: Any,
    ) -> Dict[str, ClauseResearch]:
        # Initialise board so the UI shows all clauses as "queued" immediately.
        board: Dict[str, Tuple[str, str]] = {
            b.clause_id: ("queued", b.clause_type) for b in work_blocks
        }
        _emit(progress, "research",
              f"⚡ Launching {total_work} clause workers…", 0.0, dict(board))

        done = 0
        max_workers = min(6, total_work)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self._process_clause,
                    block, is_rerun, jurisdiction, web_enabled, deadline,
                ): block
                for block in work_blocks
            }
            for future in as_completed(futures):
                block = futures[future]
                try:
                    result, triggered_web = future.result()
                    new_context[block.clause_id] = result
                    board[block.clause_id] = ("done", block.clause_type)
                except Exception as exc:
                    log.warning("Parallel research failed for %s: %s", block.clause_id, exc)
                    new_context[block.clause_id] = ClauseResearch(
                        clause_id=block.clause_id,
                        local_context=f"Research error: {str(exc)[:120]}",
                        web_results=[],
                    )
                    board[block.clause_id] = ("error", block.clause_type)

                done += 1
                _emit(progress, "research",
                      f"⚡ {done}/{total_work} done · {block.clause_type}",
                      done / total_work, dict(board))

        return new_context

    # ── Per-clause processor (used by both paths) ───────────────────────

    def _process_clause(
        self,
        block: ClauseBlock,
        is_rerun: bool,
        jurisdiction: str,
        web_enabled: bool,
        deadline: float,
    ) -> Tuple[ClauseResearch, bool]:
        """Retrieve context for one clause with an internal reflection loop."""
        local = self._research_clause(block)

        # Internal reflection: if context is thin, retry with broader queries
        # (up to 2 attempts) before falling back to web research.
        MAX_INTERNAL_REFLECTIONS = 2
        for attempt in range(1, MAX_INTERNAL_REFLECTIONS + 1):
            if self._context_quality(local, block) >= 0.35:
                break
            broader = self._research_clause_broad(block, attempt)
            if len(broader.strip()) > len(local.strip()):
                local = broader

        web_results: List[WebResult] = []
        triggered_web = False
        if (web_enabled and _WEB_AVAILABLE and self.web_subagent is not None
                and self._should_web(block, local, jurisdiction, force=is_rerun)):
            if time.monotonic() < deadline:
                triggered_web = True
                web_results = self.web_subagent.research(
                    block=block,
                    jurisdiction=jurisdiction,
                    allow_tier2=is_rerun,
                )
            else:
                log.info("per-doc web budget exhausted; skipping web for %s", block.clause_id)

        return ClauseResearch(
            clause_id=block.clause_id,
            local_context=local,
            web_results=web_results,
        ), triggered_web

    # ── Low-level retrieval helpers ─────────────────────────────────────

    def _research_clause(self, block: ClauseBlock) -> str:
        try:
            result = self.retrieval_tool._run(
                query=block.content[:300],
                clause_type=block.clause_type if block.clause_type != "miscellaneous" else None,
                num_results=3,
            )
            return result or ""
        except Exception as e:
            return f"Research error: {str(e)[:120]}"

    def _research_clause_broad(self, block: ClauseBlock, attempt: int) -> str:
        """Retry retrieval with a progressively broader query."""
        try:
            if attempt == 1:
                query = block.content[:500]
                num_results = 5
            else:
                query = (
                    f"{block.clause_type} clause legal implications "
                    f"{block.content[:200]}"
                )
                num_results = 6
            result = self.retrieval_tool._run(
                query=query,
                clause_type=block.clause_type if block.clause_type != "miscellaneous" else None,
                num_results=num_results,
            )
            return result or ""
        except Exception as e:
            return f"Research error: {str(e)[:120]}"

    @staticmethod
    def _context_quality(context: str, block: ClauseBlock) -> float:
        """Simple 0-1 quality heuristic: length + keyword overlap."""
        if not context or len(context.strip()) < 50:
            return 0.0
        length_score = min(0.5, len(context) / (2 * _THIN_LOCAL_THRESHOLD))
        clause_words = set(block.content.lower().split())
        ctx_words = set(context.lower().split())
        overlap = len(clause_words & ctx_words) / max(1, len(clause_words))
        return length_score + min(0.5, overlap)

    @staticmethod
    def _web_enabled(state: AgentState) -> bool:
        # Per-session override (Streamlit toggle) wins over env default.
        explicit = state.get("web_research_enabled")
        if explicit is not None:
            return bool(explicit)
        return _env_bool("WEB_RESEARCH_ENABLED", True)

    @staticmethod
    def _should_web(
        block: ClauseBlock,
        local: str,
        jurisdiction: str,
        force: bool = False,
    ) -> bool:
        if force:
            return True
        # Phase 1: with no jurisdiction we have no whitelist to search → skip.
        if jurisdiction == "unknown":
            return False
        if _STATUTE_RE.search(block.content or ""):
            return True
        if block.clause_type in HIGH_STAKES_TYPES:
            return True
        if len(local) < _THIN_LOCAL_THRESHOLD:
            return True
        return False
