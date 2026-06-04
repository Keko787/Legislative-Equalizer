"""
Output Agent — generates the final plain-language report from verified analysis results.
"""

from typing import Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from .state import AgentState, ClauseAnalysis, ClauseResearch, WebResult, emit_progress as _emit

RISK_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}

WEB_DISCLAIMER = (
    "> *This analysis includes references to public legal sources retrieved "
    "live from the web. Verify all citations before acting on them.*"
)


class OutputAgent:
    """Compiles all ClauseAnalysis results into a structured, user-facing report."""

    def __init__(self, api_key: str, model: str = "gpt-5.4"):
        self.llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0.3
        )

    def run(self, state: AgentState) -> AgentState:
        """Generate the final_report and store it in state."""
        analysis_results: List[ClauseAnalysis] = state.get("analysis_results", [])
        document_type = state.get("document_type", "Legal Document")
        research_context: Dict[str, ClauseResearch] = state.get("research_context", {}) or {}
        progress = state.get("_progress")  # type: ignore[typeddict-item]

        _emit(progress, "output", "Composing report…", 0.2)

        if not analysis_results:
            state["final_report"] = (
                f"## {document_type} — Analysis Report\n\n"
                "No clauses were identified for analysis."
            )
            _emit(progress, "output", "Report ready.", 1.0)
            return state

        _emit(progress, "output", "Generating recommendations…", 0.6)
        state["final_report"] = self._build_report(
            document_type, analysis_results, research_context
        )
        _emit(progress, "output", "Report ready.", 1.0)
        return state

    # ------------------------------------------------------------------

    def _build_report(
        self,
        document_type: str,
        results: List[ClauseAnalysis],
        research_context: Dict[str, ClauseResearch],
    ) -> str:
        """Compose the markdown report."""
        high   = [r for r in results if r.risk_level == "high"]
        medium = [r for r in results if r.risk_level == "medium"]
        low    = [r for r in results if r.risk_level == "low"]

        # The disclaimer ships only when at least one clause cites web sources.
        any_web = any(
            (research_context.get(r.clause_id) and research_context[r.clause_id].web_results)
            for r in results
        )

        lines: List[str] = []
        if any_web:
            lines.append(WEB_DISCLAIMER)
            lines.append("")

        lines.extend([
            f"## {document_type} — Analysis Report",
            "",
            "### Risk Summary",
            f"| Risk Level | Clauses |",
            f"|---|---|",
            f"| 🔴 High | {len(high)} |",
            f"| 🟡 Medium | {len(medium)} |",
            f"| 🟢 Low | {len(low)} |",
            "",
        ])

        if high:
            lines.append("---")
            lines.append("### 🔴 High-Risk Clauses")
            for r in high:
                lines.extend(self._format_clause(r, research_context))

        if medium:
            lines.append("---")
            lines.append("### 🟡 Medium-Risk Clauses")
            for r in medium:
                lines.extend(self._format_clause(r, research_context))

        if low:
            lines.append("---")
            lines.append("### 🟢 Standard Clauses")
            for r in low:
                lines.extend(self._format_clause(r, research_context, compact=True))

        lines.append("---")
        lines.append(self._generate_recommendations(results))

        return "\n".join(lines)

    def _format_clause(
        self,
        r: ClauseAnalysis,
        research_context: Dict[str, ClauseResearch],
        compact: bool = False,
    ) -> List[str]:
        emoji = RISK_EMOJI.get(r.risk_level, "⚪")
        conf_pct = f"{r.confidence * 100:.0f}%" if r.confidence > 0 else "N/A"
        lines = [
            f"#### {emoji} {r.clause_type.replace('_', ' ').title()} Clause",
            f"*Confidence: {conf_pct}*",
            "",
            r.plain_summary,
            "",
        ]

        if not compact:
            if r.flags:
                lines.append("**Risk Flags:**")
                for flag in r.flags:
                    lines.append(f"- {flag}")
                lines.append("")

            if r.obligations:
                lines.append("**Key Obligations:**")
                for ob in r.obligations:
                    lines.append(f"- {ob}")
                lines.append("")

        # Sources block — shown for all risk levels so users can verify any
        # citation regardless of how the analysis was rated.
        clause_research = research_context.get(r.clause_id)
        if clause_research and clause_research.web_results:
            lines.extend(self._format_sources(clause_research.web_results))

        return lines

    @staticmethod
    def _format_sources(web_results: List[WebResult]) -> List[str]:
        tier1 = [w for w in web_results if w.tier == 1]
        tier2 = [w for w in web_results if w.tier != 1]
        out: List[str] = []

        if tier1:
            out.append("**Sources:**")
            for w in tier1:
                out.append(f"- [{w.source_name}] [{_safe_link_text(w.title)}]({w.url})")
            out.append("")

        if tier2:
            out.append(
                "**Secondary sources** "
                "*(broadened search — verify before relying):*"
            )
            for w in tier2:
                out.append(f"- [{w.source_name}] [{_safe_link_text(w.title)}]({w.url})")
            out.append("")

        return out

    def _generate_recommendations(self, results: List[ClauseAnalysis]) -> str:
        """Ask the LLM to generate 3-5 actionable recommendations."""
        high_flags = []
        for r in results:
            if r.risk_level == "high":
                high_flags.extend(r.flags)

        if not high_flags:
            return (
                "### Recommendations\n\n"
                "No high-risk clauses were identified. "
                "Review medium-risk clauses with a legal professional before signing."
            )

        prompt = f"""A legal document was analyzed. The following high-risk flags were found:
{chr(10).join(f'- {f}' for f in high_flags[:10])}

Write 3-5 concise, actionable recommendations for a non-lawyer reviewing this document.
Use plain English. Format as a numbered list. No preamble."""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return f"### Recommendations\n\n{response.content.strip()}"
        except Exception:
            return (
                "### Recommendations\n\n"
                "1. Have a qualified attorney review all high-risk clauses before signing.\n"
                "2. Negotiate caps on liability and indemnification obligations.\n"
                "3. Clarify any ambiguous termination and notice provisions."
            )


def _safe_link_text(text: str) -> str:
    """Strip square brackets from titles so they don't break markdown link syntax."""
    if not text:
        return "(untitled)"
    return text.replace("[", "(").replace("]", ")")
