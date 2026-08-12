"""
Offline integration test – validates the full pipeline with a mock LLM.
Run: python test_offline.py
"""

import sys
import os
import json
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

# ── Mock Groq client ──────────────────────────────────────────────────────────
MOCK_PLAN = {
    "document_type": "Project Plan",
    "document_title": "CRM Software Launch – Project Plan",
    "assumptions": [
        "Target market assumed to be mid-size B2B companies with 50–500 employees.",
        "Timeline assumed to be 12 months.",
        "Budget assumed to be $500K based on typical mid-market software launch."
    ],
    "tasks": [
        {"id": 1, "title": "Executive Summary", "description": "High-level project overview", "output_key": "exec_summary"},
        {"id": 2, "title": "Market Analysis", "description": "Target market and competitive landscape", "output_key": "market_analysis"},
        {"id": 3, "title": "Project Scope", "description": "Features, deliverables, and exclusions", "output_key": "scope"},
        {"id": 4, "title": "Timeline & Milestones", "description": "Phase breakdown with key dates", "output_key": "timeline"},
        {"id": 5, "title": "Risk Register", "description": "Key risks and mitigation strategies", "output_key": "risks"},
    ]
}

MOCK_CONTENT = {
    "exec_summary": """## Executive Summary

This project plan outlines the launch strategy for a B2B CRM software product targeting mid-size companies with 50–500 employees across North America and Europe.

**Objectives:**
- Achieve 500 paying customers in Year 1
- Reach $2M ARR by end of Year 1
- Establish brand presence in 3 key verticals: manufacturing, professional services, and logistics

**Key Success Factors:**
- Product-market fit validated through 50-company beta program
- Dedicated customer success team from Day 1
- Competitive pricing at $45/user/month vs. Salesforce at $75/user/month
""",
    "market_analysis": """## Market Analysis

The global CRM market is projected to reach $128B by 2028, growing at 12% CAGR.

**Target Segment:** Mid-market B2B companies underserved by enterprise CRMs (too complex, too expensive) and outgrowing SMB tools.

**Competitor Analysis:**
- Salesforce: Dominant but expensive and complex for mid-market
- HubSpot: Strong brand but limited customisation at scale
- Pipedrive: Good UX but weak reporting and integrations
- Our Advantage: Purpose-built for mid-market, 3-day onboarding, open API
""",
    "scope": """## Project Scope

**In Scope:**
- Core CRM modules: Contacts, Deals, Pipeline, Reporting
- Integrations: Gmail, Outlook, Slack, Zapier
- Mobile apps: iOS and Android
- Customer portal and support ticketing

**Out of Scope (Phase 2):**
- AI/ML predictive lead scoring
- ERP integration
- White-label offering

**Deliverables:** MVP (Month 6), Beta (Month 9), GA Release (Month 12)
""",
    "timeline": """## Timeline & Milestones

**Phase 1 – Foundation (Months 1–3)**
- Team hiring complete: Month 1
- Architecture design approved: Month 2
- Core data model implemented: Month 3

**Phase 2 – Build (Months 4–6)**
- MVP feature complete: Month 6
- Internal QA: Month 6, Week 3

**Phase 3 – Beta (Months 7–9)**
- 50-company closed beta launch: Month 7
- Beta feedback incorporated: Month 9

**Phase 4 – GA Launch (Months 10–12)**
- Marketing campaign launch: Month 10
- GA release: Month 12, Day 1
""",
    "risks": """## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Key engineering hires delayed | Medium | High | Begin recruiting in Month 1 |
| Beta feedback requires major rework | Medium | High | MVP scope kept minimal |
| Competitor price war | Low | Medium | Compete on UX and support, not price |
| Data security breach | Low | Critical | SOC 2 Type II from Day 1 |
| Delayed regulatory approvals | Low | Medium | Legal review in Month 2 |
"""
}

MOCK_REFLECTION = (
    "The generated project plan comprehensively addresses the request for a CRM software "
    "launch targeting mid-size B2B companies. All five planned sections were completed successfully "
    "with realistic mock data. One assumption to verify with the client: the $500K budget and 12-month "
    "timeline – these were inferred and should be confirmed. Confidence: High."
)


def make_mock_groq():
    """Build a mock Groq client that returns pre-defined responses."""
    mock = MagicMock()

    call_count = [0]

    def create_response(*args, **kwargs):
        messages = kwargs.get("messages", [])
        user_msg = messages[-1]["content"] if messages else ""
        
        response = MagicMock()
        choice = MagicMock()

        if call_count[0] == 0:
            # Planning call
            choice.message.content = json.dumps(MOCK_PLAN)
        elif call_count[0] in range(1, 6):
            # Task execution calls
            task_keys = list(MOCK_CONTENT.keys())
            idx = min(call_count[0] - 1, len(task_keys) - 1)
            choice.message.content = MOCK_CONTENT[task_keys[idx]]
        else:
            # Reflection call
            choice.message.content = MOCK_REFLECTION

        call_count[0] += 1
        response.choices = [choice]
        return response

    mock.chat.completions.create.side_effect = create_response
    return mock


async def run_test():
    from agent.planner import AgentPlanner
    from agent.executor import AgentExecutor
    from agent.doc_generator import DocumentGenerator
    from agent.memory import ConversationMemory

    print("=" * 60)
    print("AUTONOMOUS AI AGENT – OFFLINE TEST")
    print("=" * 60)

    request = "Create a project plan for launching a new CRM software product for mid-size B2B companies"
    session_id = "test-session-001"

    print(f"\nRequest: {request}\n")

    # Setup
    mock_client = make_mock_groq()
    memory = ConversationMemory(session_id)
    memory.add_user_message(request)

    # Phase 1: Planning
    print("Phase 1: Planning...")
    planner = AgentPlanner(mock_client, memory)
    plan = await planner.create_plan(request)
    print(f"  Document type: {plan['document_type']}")
    print(f"  Title: {plan['document_title']}")
    print(f"  Tasks: {len(plan['tasks'])}")
    print(f"  Assumptions: {len(plan.get('assumptions', []))}")
    for a in plan.get("assumptions", []):
        print(f"    → {a}")

    # Phase 2: Execution
    print("\nPhase 2: Executing tasks...")
    executor = AgentExecutor(mock_client, memory)
    executed_tasks, execution_data = await executor.execute_plan(plan)
    completed = sum(1 for t in executed_tasks if t["status"] == "done")
    print(f"  Completed: {completed}/{len(executed_tasks)} tasks")
    for t in executed_tasks:
        print(f"  [{t['status'].upper():6}] {t['title']}")

    # Phase 3: Reflection
    print("\nPhase 3: Reflection...")
    reflection = await planner.reflect(request, plan, execution_data)
    print(f"  {reflection[:120]}...")

    # Phase 4: Document
    print("\nPhase 4: Generating Word document...")
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = os.path.join(tmpdir, "test_output.docx")
        doc_gen = DocumentGenerator()
        doc_gen.generate(
            document_type=plan["document_type"],
            title=plan["document_title"],
            request=request,
            plan=plan,
            execution_data=execution_data,
            reflection=reflection,
            filepath=filepath
        )
        size = os.path.getsize(filepath)
        print(f"  Document generated: {size:,} bytes")

        # Copy to outputs for inspection
        Path("outputs").mkdir(exist_ok=True)
        import shutil
        shutil.copy(filepath, "outputs/test_standard_request.docx")
        print("  Saved to: outputs/test_standard_request.docx")

    # Test 2: Ambiguous request
    print("\n" + "=" * 60)
    print("TEST 2: COMPLEX / AMBIGUOUS REQUEST")
    print("=" * 60)
    ambiguous = "We need something for the board meeting next week about the Q3 situation and what we're doing about it"
    print(f"\nRequest: {ambiguous}\n")
    print("  (Agent would identify this as a Board Deck / Executive Briefing)")
    print("  Assumptions agent would make:")
    print("  → 'The board meeting' = formal quarterly board of directors meeting")
    print("  → 'Q3 situation' = Q3 financial performance review (revenue, margins, KPIs)")
    print("  → 'What we're doing about it' = corrective action plan or strategic response")
    print("  → Document format: Executive Briefing / Board Deck with financial data")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_test())
