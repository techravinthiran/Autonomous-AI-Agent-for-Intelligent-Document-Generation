# Autonomous AI Agent for Intelligent Document Generation

## Overview

A FastAPI-based autonomous agent that accepts a natural language request, generates its own task plan, executes each step using an LLM, and produces a polished Microsoft Word document.

---

## Architecture

```
POST /agent
    │
    ▼
┌─────────────────────────────────────────────┐
│  Request Validation & Guardrails             │
│  (Pydantic validators – min/max length)      │
└────────────────────┬────────────────────────┘
                     │
    ┌────────────────▼────────────────────┐
    │  Conversation Memory                │
    │  (File-backed session history)      │
    │  → Provides context for multi-turn  │
    └────────────────┬────────────────────┘
                     │
    ┌────────────────▼────────────────────┐
    │  Phase 1 – AgentPlanner             │
    │  LLM call → structured JSON plan    │
    │  - document_type, document_title    │
    │  - assumptions (for ambiguous req.) │
    │  - task list with output_keys       │
    │  Retry × 3 + fallback plan          │
    └────────────────┬────────────────────┘
                     │
    ┌────────────────▼────────────────────┐
    │  Phase 2 – AgentExecutor            │
    │  Sequential task execution          │
    │  - Each task gets prior context     │
    │  - Retry × 2 per task + fallback    │
    │  - Accumulates section content      │
    └────────────────┬────────────────────┘
                     │
    ┌────────────────▼────────────────────┐
    │  Phase 3 – Reflection / Self-Check  │
    │  LLM reviews completeness vs req.   │
    │  Flags gaps, states confidence      │
    └────────────────┬────────────────────┘
                     │
    ┌────────────────▼────────────────────┐
    │  Phase 4 – DocumentGenerator        │
    │  python-docx → polished .docx       │
    │  Cover, metadata, task table,       │
    │  content sections, quality review   │
    └────────────────┬────────────────────┘
                     │
    ┌────────────────▼────────────────────┐
    │  AgentResponse JSON + /document/    │
    │  download URL                       │
    └─────────────────────────────────────┘
```

---

## Engineering Improvement: Multi-Step Planning + Reflection/Self-Check

### What was implemented
Two improvements working together:

1. **Multi-step planning** – The agent first makes a dedicated LLM call to produce a structured JSON plan (document type, title, task list, assumptions) *before* any execution begins. Tasks are ordered so each builds on the previous, with accumulated context passed forward.

2. **Reflection/Self-Check** – After execution, a second LLM call reviews the original request against what was produced, assessing completeness, flagging gaps, and stating a confidence level. This self-check is included in the final document.

### Why I chose this
- Separating planning from execution dramatically improves output coherence – the agent commits to a strategy before writing anything.
- Self-check catches obvious mismatches (e.g. a marketing plan request that somehow produced an IT report) without requiring human review.
- Both improve auditability: users can see *what* the agent planned and *whether* it thinks it succeeded.

### How it improves the agent
- Plans are transparent and inspectable in the API response (`task_list`).
- Ambiguous requests get explicit assumptions rather than silent hallucinations.
- Reflection gives users a quick quality signal and flags when to request clarification.

---

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Groq API key (free at console.groq.com)

Create a `.env` file in the project root:
```
GROQ_API_KEY=gsk_your_key_here
```

Or set it as an environment variable:
```bash
export GROQ_API_KEY="gsk_your_key_here"
```

### 3. Start the server
```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Or using Python directly:
```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### 4. (Optional) Start the Streamlit Frontend

For a user-friendly web interface, start the Streamlit app in a separate terminal:
```bash
streamlit run streamlit_app.py
```

**Note:** Both the FastAPI server (port 8000) and Streamlit (port 8501) must run simultaneously for the frontend to work.

The Streamlit UI provides:
- Easy-to-use form for entering requests
- Real-time task progress display with expandable details
- Document download button
- Visual feedback and error handling
- Metrics showing document type and completion status

---

## API

### POST /agent
```json
{
  "request": "Create a project plan for launching a mobile payment app in India",
  "session_id": "optional-uuid-for-multi-turn"
}
```

Response includes:
- `task_list` – the agent's planned steps with statuses
- `assumptions_made` – clarifications for ambiguous inputs
- `reflection` – self-check quality assessment
- `document_url` – `/document/{filename}` to download the Word doc

### GET /document/{filename}
Downloads the generated .docx file.

### GET /sessions/{session_id}
Returns conversation history for a session.

---

## Test Cases

### Standard Request
```json
{"request": "Create a project plan for launching a new CRM software product for mid-size B2B companies"}
```

### Complex / Ambiguous Request
```json
{"request": "We need something for the board meeting next week about the Q3 situation and what we're doing about it"}
```
This request is deliberately vague – the agent will state its assumptions (board meeting format, Q3 financial review, action plan structure) before generating the document.

---

## Technology Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| API framework | FastAPI | Async, Pydantic validation, OpenAPI docs built-in |
| Frontend UI | Streamlit | User-friendly web interface for document generation |
| LLM | Groq (llama3-8b-8192) | Free tier, fast inference |
| Document generation | python-docx | Full .docx control, no external services |
| Memory | File-backed JSON | Zero-dependency, session-scoped |
| Validation | Pydantic v2 | Input guardrails at the model layer |

---

## Engineering Tradeoffs

### Autonomous Planning vs Deterministic Workflows

**The tradeoff:** A deterministic workflow (fixed steps per document type) is predictable, testable, and fast. An autonomous plan (LLM decides the steps) is flexible but non-deterministic.

**Decision:** Autonomous planning with a deterministic fallback. The LLM generates the task list but a hard-coded fallback kicks in if JSON parsing fails after 3 attempts. This gives flexibility for novel request types while maintaining reliability.

**Cost:** Autonomous plans are harder to unit-test and can vary across identical inputs. In production I would add plan validation schemas and a plan-type registry to narrow the search space.

---

## File Structure

```
docx-gen-ai-agent/
├── main.py                  # FastAPI app, routes, request/response models
├── streamlit_app.py         # Streamlit frontend UI
├── requirements.txt         # Python dependencies
├── README.md                # This file
├── .env                     # API keys (not in git)
├── .gitignore               # Git ignore rules
├── LICENSE                  # MIT License
├── agent/
│   ├── __init__.py
│   ├── planner.py           # Phase 1 (plan) + Phase 3 (reflect)
│   ├── executor.py          # Phase 2 (execute tasks sequentially)
│   ├── doc_generator.py     # Phase 4 (generate Word document)
│   └── memory.py            # Conversation memory (session persistence)
├── outputs/                 # Generated .docx files
├── memory_store/            # Session message history (JSON files)
└── env/                     # Python virtual environment (not in git)
```
