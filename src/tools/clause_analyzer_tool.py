"""
Clause Analyzer Tool for the Legal Assistant Agent.
Uses Gemini to identify risk flags, obligations, and produce plain-language summaries.
"""

import json
from typing import Optional, List
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ConfigDict


class ClauseAnalyzerInput(BaseModel):
    """Input schema for the clause analyzer tool."""
    clause_type: str = Field(description="Type of clause (e.g. termination, liability)")
    content: str = Field(description="Raw clause text to analyze")
    research_context: str = Field(
        default="",
        description="Additional legal context retrieved for this clause"
    )


class ClauseAnalyzerTool(BaseTool):
    """Analyzes a legal clause for risks, obligations, and plain-language meaning."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = "clause_analyzer"
    description: str = """Analyze a legal clause to identify:
    - Risk level (low / medium / high)
    - Specific risk flags (e.g. uncapped liability, auto-renewal traps)
    - Obligations imposed on each party
    - A plain-language summary suitable for non-lawyers
    """
    args_schema: type = ClauseAnalyzerInput

    def __init__(self, api_key: str, model: str = "gpt-5.4"):
        super().__init__()
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "llm", ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0.2
        ))

    def _run(
        self,
        clause_type: str,
        content: str,
        research_context: str = ""
    ) -> dict:
        """Analyze a clause and return structured results as a dict."""

        context_section = (
            f"\nAdditional Legal Context:\n{research_context}\n"
            if research_context else ""
        )

        prompt = f"""You are a legal expert analyzing a clause for non-lawyers.

Clause Type: {clause_type}

Clause Text:
{content}
{context_section}

Analyze this clause and respond in valid JSON only (no markdown, no extra text):
{{
  "risk_level": "low" | "medium" | "high",
  "flags": ["concise flag 1", "concise flag 2"],
  "obligations": ["obligation 1 in plain language", "obligation 2"],
  "plain_summary": "2-3 sentence plain-English explanation of what this clause means and why it matters"
}}

Rules:
- risk_level "high" = significant financial, legal, or operational exposure
- risk_level "medium" = notable obligations or one-sided terms
- risk_level "low" = standard, balanced terms
- flags should be short (under 10 words each)
- obligations should start with who must do what
- plain_summary must be understandable to someone with no legal training"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            text = response.content.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            return {
                "risk_level": "medium",
                "flags": [f"Analysis error: {str(e)[:60]}"],
                "obligations": [],
                "plain_summary": f"Could not analyze this clause automatically: {str(e)[:120]}"
            }

    async def _arun(self, clause_type: str, content: str, research_context: str = "") -> dict:
        return self._run(clause_type, content, research_context)
