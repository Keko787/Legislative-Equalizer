"""
Evaluator Tool for the Legal Assistant Agent.
Scores the confidence of a clause analysis against its source evidence.
"""

import json
from typing import List
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field, ConfigDict


class EvaluatorInput(BaseModel):
    """Input schema for the evaluator tool."""
    clause_type: str = Field(description="Type of clause being evaluated")
    original_content: str = Field(description="Original clause text")
    analysis_json: str = Field(description="JSON string of the ClauseAnalyzerTool output")
    research_context: str = Field(default="", description="Research context used for analysis")


class EvaluatorTool(BaseTool):
    """Scores the quality and confidence of a clause analysis."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = "analysis_evaluator"
    description: str = """Evaluate the quality of a legal clause analysis by checking:
    - Whether the risk level is justified by the clause content
    - Whether identified flags are grounded in the actual text
    - Whether obligations are accurately extracted
    - Overall confidence in the analysis (0.0 to 1.0)
    """
    args_schema: type = EvaluatorInput

    def __init__(self, api_key: str, model: str = "gpt-5.4"):
        super().__init__()
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "llm", ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0.1
        ))

    def _run(
        self,
        clause_type: str,
        original_content: str,
        analysis_json: str,
        research_context: str = ""
    ) -> dict:
        """Evaluate analysis quality. Returns dict with score and reasoning."""

        context_section = (
            f"\nResearch Context Used:\n{research_context}\n"
            if research_context else ""
        )

        prompt = f"""You are a senior legal reviewer checking the quality of a junior analyst's work.

Original Clause ({clause_type}):
{original_content}
{context_section}
Analysis Produced:
{analysis_json}

Evaluate this analysis and respond in valid JSON only (no markdown, no extra text):
{{
  "confidence": 0.85,
  "reasoning": "One sentence explaining the confidence score",
  "failure_mode": null,
  "issues": ["issue 1 if any", "issue 2 if any"]
}}

Scoring guide:
- 0.9–1.0: Analysis is accurate, well-grounded, and complete
- 0.7–0.89: Mostly correct with minor gaps or imprecisions
- 0.5–0.69: Some correct points but notable inaccuracies or missing items
- below 0.5: Significant errors or hallucinations present

failure_mode rules:
- null  — confidence >= 0.70 (no failure)
- "missing_context" — analysis is reasonable but the research context was thin or did not cover the clause's specific statute, jurisdiction, or terminology
- "weak_reasoning" — context appeared adequate but the analysis itself is inconsistent, contradicts the clause, hallucinates, or misclassifies risk

issues should be empty list [] if confidence >= 0.75"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            text = response.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            result = json.loads(text.strip())
            # Clamp confidence to [0, 1]
            result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.5))))
            return result
        except Exception as e:
            return {
                "confidence": 0.5,
                "reasoning": f"Evaluation error: {str(e)[:120]}",
                "issues": []
            }

    async def _arun(
        self,
        clause_type: str,
        original_content: str,
        analysis_json: str,
        research_context: str = ""
    ) -> dict:
        return self._run(clause_type, original_content, analysis_json, research_context)
