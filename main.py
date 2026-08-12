"""
Autonomous AI Agent - Python AI Engineer Assignment
FastAPI + Groq (free LLM) + python-docx
Engineering Improvement: Multi-step planning with reflection/self-check
"""

import os
import json
import uuid
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel, validator
from groq import Groq

from agent.planner import AgentPlanner
from agent.executor import AgentExecutor
from agent.doc_generator import DocumentGenerator
from agent.memory import ConversationMemory

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("agent")

# ─── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Autonomous AI Agent",
    description="Natural language → task plan → Word document",
    version="1.0.0"
)

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# ─── Models ────────────────────────────────────────────────────────────────────
class AgentRequest(BaseModel):
    request: str
    session_id: Optional[str] = None

    @validator("request")
    def request_must_not_be_empty(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Request cannot be empty")
        if len(v) < 10:
            raise ValueError("Request too short – please provide more detail")
        if len(v) > 2000:
            raise ValueError("Request too long – max 2000 characters")
        return v


class TaskItem(BaseModel):
    id: int
    title: str
    description: str
    status: str  # pending | running | done | failed


class AgentResponse(BaseModel):
    session_id: str
    request: str
    document_type: str
    task_list: list[TaskItem]
    execution_summary: str
    reflection: str
    document_filename: str
    document_url: str
    assumptions_made: list[str]
    total_steps: int
    completed_steps: int
    timestamp: str


# ─── Routes ────────────────────────────────────────────────────────────────────
@app.get("/")
def root():
    return {
        "service": "Autonomous AI Agent",
        "endpoints": {
            "POST /agent": "Submit a natural language request",
            "GET /document/{filename}": "Download generated Word document",
            "GET /sessions/{session_id}": "Get session history",
        }
    }


@app.post("/agent", response_model=AgentResponse)
async def run_agent(body: AgentRequest):
    session_id = body.session_id or str(uuid.uuid4())
    logger.info(f"[{session_id}] New request: {body.request[:80]}...")

    # Load conversation memory for this session
    memory = ConversationMemory(session_id)
    memory.add_user_message(body.request)

    groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", ""))

    # ── Phase 1: Planning ──────────────────────────────────────────────────────
    logger.info(f"[{session_id}] Phase 1: Planning")
    planner = AgentPlanner(groq_client, memory)
    plan = await planner.create_plan(body.request)

    logger.info(f"[{session_id}] Plan: {plan['document_type']}, {len(plan['tasks'])} tasks")

    # ── Phase 2: Execution ────────────────────────────────────────────────────
    logger.info(f"[{session_id}] Phase 2: Executing {len(plan['tasks'])} tasks")
    executor = AgentExecutor(groq_client, memory)
    executed_tasks, execution_data = await executor.execute_plan(plan)

    completed = sum(1 for t in executed_tasks if t["status"] == "done")
    logger.info(f"[{session_id}] Execution done: {completed}/{len(executed_tasks)} tasks")

    # ── Phase 3: Reflection / Self-Check ─────────────────────────────────────
    logger.info(f"[{session_id}] Phase 3: Reflection & self-check")
    reflection = await planner.reflect(body.request, plan, execution_data)

    # ── Phase 4: Document Generation ─────────────────────────────────────────
    logger.info(f"[{session_id}] Phase 4: Generating Word document")
    doc_gen = DocumentGenerator()
    filename = f"{session_id}_{plan['document_type'].replace(' ', '_')}.docx"
    filepath = OUTPUT_DIR / filename

    doc_gen.generate(
        document_type=plan["document_type"],
        title=plan["document_title"],
        request=body.request,
        plan=plan,
        execution_data=execution_data,
        reflection=reflection,
        filepath=str(filepath)
    )

    memory.add_assistant_message(
        f"Generated {plan['document_type']}: {plan['document_title']}"
    )

    task_items = [
        TaskItem(
            id=i + 1,
            title=t["title"],
            description=t["description"],
            status=t["status"]
        )
        for i, t in enumerate(executed_tasks)
    ]

    return AgentResponse(
        session_id=session_id,
        request=body.request,
        document_type=plan["document_type"],
        task_list=task_items,
        execution_summary=execution_data.get("summary", ""),
        reflection=reflection,
        document_filename=filename,
        document_url=f"/document/{filename}",
        assumptions_made=plan.get("assumptions", []),
        total_steps=len(executed_tasks),
        completed_steps=completed,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


@app.get("/document/{filename}")
async def download_document(filename: str):
    filepath = OUTPUT_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    return FileResponse(
        path=str(filepath),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@app.get("/sessions/{session_id}")
async def get_session(session_id: str):
    memory = ConversationMemory(session_id)
    return {
        "session_id": session_id,
        "messages": memory.get_history(),
        "message_count": len(memory.get_history())
    }
