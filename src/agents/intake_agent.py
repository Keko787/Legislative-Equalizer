"""
Intake Agent — parses and segments the document into typed clause blocks.
This is the first node in the DAG.
"""

import json
import re
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from .state import AgentState, ClauseBlock, emit_progress as _emit

# Known clause types the agent recognises
CLAUSE_TYPES = [
    "termination", "payment", "liability", "confidentiality",
    "indemnification", "intellectual property", "force majeure",
    "governing law", "notice", "warranties", "dispute resolution",
    "non-compete", "assignment", "amendment", "miscellaneous"
]

KEYWORD_MAP = {
    "termination":          ["terminat", "end of agreement", "cancel"],
    "payment":              ["payment", "invoice", "fee", "compensation", "reimburse"],
    "liability":            ["liabilit", "liable", "cap on damages", "limitation of liability"],
    "confidentiality":      ["confidential", "non-disclosure", "nda", "proprietary"],
    "indemnification":      ["indemnif", "hold harmless"],
    "intellectual property":["intellectual property", " ip ", "copyright", "patent", "trademark"],
    "force majeure":        ["force majeure", "act of god", "natural disaster"],
    "governing law":        ["governing law", "jurisdiction", "applicable law"],
    "notice":               ["notice", "notification", "written notice"],
    "warranties":           ["warrant", "representation", "guaranty"],
    "dispute resolution":   ["arbitrat", "mediat", "dispute", "litigation"],
    "non-compete":          ["non-compete", "non compete", "noncompete", "restrictive covenant"],
    "assignment":           ["assign", "transfer of rights"],
    "amendment":            ["amendment", "modification", "change to this agreement"],
}


class IntakeAgent:
    """Parses a document, identifies its type, and segments it into clause blocks."""

    def __init__(self, api_key: str, model: str = "gpt-5.4"):
        self.llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0.1
        )

    def run(self, state: AgentState) -> AgentState:
        """Execute intake analysis. Updates state with document_type and clause_blocks."""
        document_text = state.get("document_text", "")
        progress = state.get("_progress")  # type: ignore[typeddict-item]

        if not document_text.strip():
            state["error"] = "Intake Agent: empty document_text"
            state["document_type"] = "Unknown"
            state["clause_blocks"] = []
            return state

        _emit(progress, "intake", "Identifying document type…", 0.0)
        state["document_type"] = self._identify_document_type(document_text)
        _emit(progress, "intake", "Detecting jurisdiction…", 0.4)
        state["jurisdiction"] = self._identify_jurisdiction(document_text)
        _emit(progress, "intake", "Segmenting clauses…", 0.8)
        state["clause_blocks"] = self._segment_clauses(document_text)
        _emit(progress, "intake",
              f"Intake complete · {len(state['clause_blocks'])} blocks · "
              f"jurisdiction={state['jurisdiction']}", 1.0)
        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _identify_document_type(self, text: str) -> str:
        """Use the LLM to identify the document type from the first ~800 chars."""
        snippet = text[:800]
        prompt = f"""Read the opening of this legal document and identify its type.

Document opening:
{snippet}

Reply with the document type only — e.g. "Professional Services Agreement",
"Non-Disclosure Agreement", "Employment Contract", "Lease Agreement", etc.
If unsure, reply "General Legal Agreement"."""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content.strip().strip('"').strip("'")
        except Exception:
            return "General Legal Agreement"

    def _identify_jurisdiction(self, text: str) -> str:
        """
        Use the LLM to classify the document's governing jurisdiction.
        Returns one of: "IN", "UK", "US", "EU", "unknown".
        """
        # Look at both ends — governing-law clauses are often at the bottom
        snippet = text[:1500] + "\n...\n" + text[-1500:] if len(text) > 3000 else text

        prompt = f"""Identify the legal jurisdiction governing this document.
Look for explicit "governing law" / "jurisdiction" clauses, references to
specific statutes, courts, currencies, or regional conventions.

Document excerpt:
{snippet}

Reply with EXACTLY ONE of these tokens (no other text):
IN       — India
UK       — United Kingdom
US       — United States (federal or state)
EU       — European Union member state
unknown  — cannot determine from the text"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            raw = response.content.strip().strip('"').strip("'").upper()
            # Defensive parse — accept the first valid token in the response
            for token in ("IN", "UK", "US", "EU"):
                if token in raw.split():
                    return token
            return "unknown"
        except Exception:
            return "unknown"

    def _segment_clauses(self, text: str) -> List[ClauseBlock]:
        """Split text into chunks and tag each with the best-matching clause type."""
        # Split only at top-level section markers: numbered headings like "1.",
        # "12." but NOT sub-section numbering like "1.1", "2.3" — handled by
        # the negative lookahead `(?!\d)` after the period. Also matches
        # lettered headings "(a)" and ALL-CAPS / SECTION/ARTICLE/CLAUSE
        # keywords at line start.
        sections = re.split(
            r'\n(?=\s*(?:\d+\.(?!\d)|\([a-z]\)|[A-Z]{2,}|\b(?:SECTION|ARTICLE|CLAUSE)\b))',
            text
        )
        # Fallback: split on double newlines
        if len(sections) <= 2:
            sections = [s.strip() for s in text.split("\n\n") if s.strip()]

        blocks: List[ClauseBlock] = []
        for i, section in enumerate(sections):
            if len(section.strip()) < 30:
                continue
            clause_type = self._classify_section(section)
            blocks.append(ClauseBlock(
                clause_id=f"clause_{i:03d}",
                clause_type=clause_type,
                content=section.strip(),
                chunk_id=i
            ))

        return blocks

    def _classify_section(self, text: str) -> str:
        """Keyword-match a section to the most relevant clause type."""
        text_lower = text.lower()
        best_type = "miscellaneous"
        best_count = 0

        for clause_type, keywords in KEYWORD_MAP.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > best_count:
                best_count = count
                best_type = clause_type

        return best_type


