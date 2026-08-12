"""
Agent Planner – Phase 1 (Planning) and Phase 3 (Reflection / Self-Check)

Engineering Improvement: Multi-step planning + Reflection/Self-Check
- Planner first determines WHAT type of document is needed and makes assumptions
  for ambiguous requests before generating the task list.
- After execution, a second LLM call reviews the output for completeness and
  flags anything missing – this is the self-check loop.
"""

import json
import logging
from typing import Dict, Any

from groq import Groq
from agent.memory import ConversationMemory

logger = logging.getLogger("agent.planner")

PLANNING_SYSTEM = """You are an expert autonomous AI agent planner.
Your job is to analyse a user request, identify what kind of business document
is needed, make reasonable assumptions for anything ambiguous, and generate
a structured execution plan.

Respond ONLY with valid JSON matching this schema exactly:
{
  "document_type": "<type, e.g. Project Plan, Business Report, SOP, Meeting Minutes>",
  "document_title": "<specific title for this document>",
  "assumptions": ["<assumption 1>", "<assumption 2>"],
  "tasks": [
    {
      "id": 1,
      "title": "<short task title>",
      "description": "<what this task will produce>",
      "output_key": "<snake_case key to store result>"
    }
  ]
}

Rules:
- Always include 4-8 tasks covering research/data gathering, analysis, writing sections, and final review.
- Tasks must be sequential and build on each other.
- If the request is ambiguous or missing information, list your assumptions.
- output_key must be unique per task.
- Keep task descriptions concise but specific.
"""

REFLECTION_SYSTEM = """You are a quality assurance reviewer for an AI agent.
Given the original request, the plan, and the execution results, provide a
brief self-check assessment.

Respond with 2-4 sentences covering:
1. Whether the output adequately addresses the original request.
2. Any gaps or assumptions that should be flagged to the user.
3. Confidence level (High / Medium / Low) and why.
"""


class AgentPlanner:
    def __init__(self, client: Groq, memory: ConversationMemory):
        self.client = client
        self.memory = memory

    async def create_plan(self, request: str) -> Dict[str, Any]:
        """
        Call the LLM to produce a structured plan with tasks, document type,
        title, and any assumptions made for ambiguous inputs.
        """
        context = self.memory.get_context_summary()

        user_prompt = f"""{context}

Current request:
\"\"\"{request}\"\"\"

Analyse the request. If it's ambiguous, complex, or missing details, state
your assumptions explicitly. Then produce the full JSON execution plan."""

        # Retry up to 3 times if JSON parsing fails (error recovery)
        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": PLANNING_SYSTEM},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1500,
                )
                raw = response.choices[0].message.content.strip()

                # Strip markdown fences if present
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]

                plan = json.loads(raw)
                self._validate_plan(plan)
                return plan

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                logger.warning(f"Planning attempt {attempt+1} failed: {e}")
                if attempt == 2:
                    # Final fallback: return a generic plan
                    logger.error("All planning attempts failed; using fallback plan")
                    return self._fallback_plan(request)

        return self._fallback_plan(request)

    def _validate_plan(self, plan: dict):
        required = ["document_type", "document_title", "tasks"]
        for key in required:
            if key not in plan:
                raise ValueError(f"Missing key in plan: {key}")
        if not isinstance(plan["tasks"], list) or len(plan["tasks"]) == 0:
            raise ValueError("tasks must be a non-empty list")
        for t in plan["tasks"]:
            for k in ["id", "title", "description", "output_key"]:
                if k not in t:
                    raise ValueError(f"Task missing key: {k}")

    def _fallback_plan(self, request: str) -> Dict[str, Any]:
        """Deterministic fallback plan when LLM fails repeatedly."""
        return {
            "document_type": "Business Report",
            "document_title": f"Report: {request[:60]}",
            "assumptions": [
                "Request could not be parsed precisely; generic business report structure used.",
                "All sections populated with best-effort content."
            ],
            "tasks": [
                {"id": 1, "title": "Understand Request", "description": "Parse and clarify the user request", "output_key": "understanding"},
                {"id": 2, "title": "Gather Background", "description": "Collect relevant context and data", "output_key": "background"},
                {"id": 3, "title": "Analyse Findings", "description": "Analyse gathered information", "output_key": "analysis"},
                {"id": 4, "title": "Draft Recommendations", "description": "Produce actionable recommendations", "output_key": "recommendations"},
                {"id": 5, "title": "Executive Summary", "description": "Write executive summary", "output_key": "exec_summary"},
            ]
        }

    async def reflect(self, request: str, plan: Dict, execution_data: Dict) -> str:
        """
        Self-check: after execution, ask the LLM whether the output sufficiently
        addresses the original request. Returns a reflection string.
        """
        exec_summary = execution_data.get("summary", "No summary available.")
        section_keys = list(execution_data.get("sections", {}).keys())

        prompt = f"""Original request: \"{request}\"

Planned document type: {plan['document_type']}
Planned tasks: {[t['title'] for t in plan['tasks']]}
Assumptions made: {plan.get('assumptions', [])}

Sections produced: {section_keys}
Execution summary: {exec_summary}

Provide your quality assessment."""

        try:
            response = self.client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": REFLECTION_SYSTEM},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=300,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"Reflection call failed: {e}")
            return "Self-check skipped due to API error. Output generated based on plan."
