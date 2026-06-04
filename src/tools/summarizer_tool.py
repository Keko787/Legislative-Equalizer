"""
Summarizer tool for the Legal Assistant Agent.
Uses Gemini API to simplify complex legal language into plain English.
"""

import os
from typing import Dict, Any, Optional
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ConfigDict


class SummarizerInput(BaseModel):
    """Input schema for the summarizer tool."""
    text: str = Field(description="Legal text to summarize or simplify")
    style: str = Field(
        default="student-friendly",
        description="Summary style: 'student-friendly', 'executive', 'technical', or 'bullet-points'"
    )
    focus: Optional[str] = Field(
        default=None,
        description="Specific aspect to focus on (e.g., 'obligations', 'risks', 'deadlines')"
    )


class SummarizerTool(BaseTool):
    """Tool for summarizing and simplifying legal text."""
    
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='allow')

    name: str = "legal_summarizer"
    description: str = """Summarize and simplify complex legal language into plain English.
    This tool can:
    1. Convert legal jargon into student-friendly language
    2. Extract key points from clauses
    3. Highlight important obligations, rights, and risks
    4. Create executive summaries
    5. Format information in bullet points

    Use this tool when the user asks for:
    - Simplified explanations of legal terms
    - Plain English summaries
    - Key takeaways from clauses
    - Student-friendly interpretations
    """
    args_schema: type = SummarizerInput

    def __init__(self, api_key: str, model: str = "gpt-5.4"):
        """Initialize the summarizer tool.

        Args:
            api_key: Google API key for Gemini
            model: Gemini model to use (default: gpt-5.4)
        """
        super().__init__()
        object.__setattr__(self, 'api_key', api_key)
        object.__setattr__(self, 'model', model)
        object.__setattr__(self, 'llm', ChatOpenAI(
            model=model,
            api_key=api_key,
            temperature=0.3
        ))

    def _run(self, text: str, style: str = "student-friendly", focus: Optional[str] = None) -> str:
        """Execute the summarization operation.

        Args:
            text: Legal text to summarize
            style: Summary style
            focus: Optional focus area

        Returns:
            Summarized and simplified text
        """
        try:
            prompt = self._create_prompt(text, style, focus)
            response = self.llm.invoke(prompt)
            
            # Clean and format the response
            cleaned_response = self._clean_response(response.content)
            return cleaned_response

        except Exception as e:
            return f"Error summarizing text: {str(e)}"

    async def _arun(self, text: str, style: str = "student-friendly", focus: Optional[str] = None) -> str:
        """Async version of the run method."""
        return self._run(text, style, focus)

    def _create_prompt(self, text: str, style: str, focus: Optional[str] = None) -> str:
        """Create the appropriate prompt for the given style and focus.

        Args:
            text: Legal text to process
            style: Summary style
            focus: Optional focus area

        Returns:
            Formatted prompt for the LLM
        """
        base_prompt = f"""You are a legal expert helping students and non-lawyers understand legal documents.

CRITICAL: Generate clean, properly formatted text with correct spacing between all words. Do NOT generate text with missing spaces between words.

Legal Text to Analyze:
{text}

"""

        if style == "student-friendly":
            style_instruction = """
Please provide a student-friendly explanation that:
1. Uses simple, everyday language
2. Avoids legal jargon or explains it when necessary
3. Uses examples or analogies when helpful
4. Highlights key points that would matter to someone without legal training
5. Explains the practical implications
6. Uses proper markdown formatting with clear sections

Format your response as:
[Your simplified explanation directly, without any "What this means in plain English" prefix]

**Key points to remember:**
- [Important point 1]
- [Important point 2]
- [etc.]

Make sure to:
- Use proper spacing between sentences
- Format currency amounts clearly (e.g., $150,000)
- Use bullet points for lists
- Keep paragraphs short and readable
- Avoid run-on sentences
"""

        elif style == "executive":
            style_instruction = """
Please provide an executive summary that:
1. Focuses on business implications and risks
2. Highlights financial and operational impacts
3. Identifies key decision points
4. Uses professional but accessible language
5. Prioritizes actionable information

Format your response as:
**Executive Summary:**
[Brief overview]

**Key Business Implications:**
- [Implication 1]
- [Implication 2]

**Action Items/Considerations:**
- [Action 1]
- [Action 2]
"""

        elif style == "bullet-points":
            style_instruction = """
Please create a bullet-point summary that:
1. Breaks down the text into digestible points
2. Uses clear, concise language
3. Organizes information logically
4. Highlights the most important elements

Format your response as bullet points with clear categories.
"""

        elif style == "technical":
            style_instruction = """
Please provide a technical analysis that:
1. Maintains legal precision while improving clarity
2. Explains the legal mechanics
3. Identifies potential issues or ambiguities
4. Provides context for legal standards

Format your response with clear sections and explanations.
"""

        else:
            style_instruction = """
Please provide a clear, accessible explanation of this legal text.
Focus on making it understandable for a general audience.
"""

        focus_instruction = ""
        if focus:
            focus_instruction = f"\nSpecial Focus: Pay particular attention to aspects related to '{focus}' in your analysis."

        return base_prompt + style_instruction + focus_instruction

    def _clean_response(self, response: str) -> str:
        """Clean and format the LLM response."""
        if not response:
            return response
            
        import re
        
        # Remove unwanted prefixes
        response = re.sub(r'^What this means in plain English:\s*', '', response, flags=re.IGNORECASE)
        response = re.sub(r'^In plain English:\s*', '', response, flags=re.IGNORECASE)
        
        # Basic text cleaning (stable model shouldn't need aggressive fixes)
        response = re.sub(r'([.!?])([A-Z])', r'\1 \2', response)  # Fix missing spaces after punctuation
        response = re.sub(r'([,])([A-Z])', r'\1 \2', response)    # Fix missing spaces after commas
        response = re.sub(r'(\d+)([A-Z])', r'\1 \2', response)    # Fix missing spaces after numbers
        
        # Fix multiple spaces but preserve line breaks
        response = re.sub(r'[ \t]+', ' ', response)
        response = re.sub(r'\n\s*\n', '\n\n', response)
        
        return response.strip()

    def compare_clauses(self, clause1: str, clause2: str, clause_types: str) -> str:
        """Compare two clauses and highlight differences.

        Args:
            clause1: First clause text
            clause2: Second clause text
            clause_types: Description of what types of clauses these are

        Returns:
            Comparison analysis
        """
        prompt = f"""You are a legal expert comparing two clauses for students to understand.

Clause Type: {clause_types}

CLAUSE 1:
{clause1}

CLAUSE 2:
{clause2}

Please provide a student-friendly comparison that:
1. Explains what each clause means in plain English
2. Highlights the key differences between them
3. Explains which might be more favorable and why
4. Uses simple language and practical examples

Format your response as:
**Clause 1 Summary:**
[Plain English explanation]

**Clause 2 Summary:**
[Plain English explanation]

**Key Differences:**
- [Difference 1]
- [Difference 2]

**Practical Impact:**
[Explanation of what these differences mean in practice]
"""

        try:
            response = self.llm.invoke(prompt)
            cleaned_response = self._clean_response(response.content)
            return cleaned_response
        except Exception as e:
            return f"Error comparing clauses: {str(e)}"

    def extract_obligations(self, text: str) -> str:
        """Extract and explain obligations from legal text.

        Args:
            text: Legal text to analyze

        Returns:
            Extracted obligations in plain English
        """
        prompt = f"""You are a legal expert helping students understand their obligations from a legal document.

Legal Text:
{text}

Please identify and explain all obligations, duties, and requirements mentioned in this text.

Format your response as:
**Your Obligations (What you must do):**
- [Obligation 1 in plain English]
- [Obligation 2 in plain English]

**Other Party's Obligations (What they must do):**
- [Their obligation 1]
- [Their obligation 2]

**Important Deadlines or Timeframes:**
- [Any time-sensitive requirements]

**Consequences of Not Complying:**
- [What happens if obligations aren't met]

Use simple language that a student would understand.
"""

        try:
            response = self.llm.invoke(prompt)
            cleaned_response = self._clean_response(response.content)
            return cleaned_response
        except Exception as e:
            return f"Error extracting obligations: {str(e)}"

    def identify_risks(self, text: str) -> str:
        """Identify and explain risks from legal text.

        Args:
            text: Legal text to analyze

        Returns:
            Risk analysis in plain English
        """
        prompt = f"""You are a legal expert helping students understand the risks in a legal document.

Legal Text:
{text}

Please identify and explain all potential risks, liabilities, and negative consequences mentioned in this text.

Format your response as:
**Potential Risks for You:**
- [Risk 1 explained simply]
- [Risk 2 explained simply]

**Financial Risks:**
- [Any monetary risks or penalties]

**Legal Risks:**
- [Legal consequences you might face]

**How to Minimize These Risks:**
- [Practical advice for risk mitigation]

Use everyday language that clearly explains what could go wrong and why it matters.
"""

        try:
            response = self.llm.invoke(prompt)
            cleaned_response = self._clean_response(response.content)
            return cleaned_response
        except Exception as e:
            return f"Error identifying risks: {str(e)}"