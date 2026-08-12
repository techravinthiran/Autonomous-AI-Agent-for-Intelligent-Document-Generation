"""
Agent Executor – Phase 2

Executes each task from the plan sequentially, passing accumulated context
from previous tasks into each new task prompt. Implements retry + fallback
error handling as the engineering improvement.
"""

import json
import logging
from typing import Dict, Any, List, Tuple

from groq import Groq
from agent.memory import ConversationMemory

logger = logging.getLogger("agent.executor")

EXECUTOR_SYSTEM = """You are an expert business analyst and writer.
You are executing one specific task as part of generating a professional business document.
Your output will be incorporated into the final document.

Guidelines:
- Be specific and professional.
- Use realistic mock data when real data is unavailable (dates, numbers, names).
- Keep output structured with clear headings and bullet points where appropriate.
- Output ONLY the content for this task – no meta-commentary.
- Length: 150-400 words per task.
"""


class AgentExecutor:
    def __init__(self, client: Groq, memory: ConversationMemory):
        self.client = client
        self.memory = memory

    async def execute_plan(
        self, plan: Dict[str, Any]
    ) -> Tuple[List[Dict], Dict[str, Any]]:
        """
        Execute all tasks in the plan sequentially.
        Returns (executed_tasks_list, execution_data_dict).
        """
        tasks = plan["tasks"]
        document_type = plan["document_type"]
        document_title = plan["document_title"]
        assumptions = plan.get("assumptions", [])

        executed_tasks = []
        sections: Dict[str, str] = {}
        accumulated_context = ""

        for task in tasks:
            task_result = await self._execute_task(
                task=task,
                document_type=document_type,
                document_title=document_title,
                original_request=self.memory.get_history()[-1]["content"] if self.memory.get_history() else "",
                accumulated_context=accumulated_context,
                assumptions=assumptions,
            )

            executed_tasks.append({
                "id": task["id"],
                "title": task["title"],
                "description": task["description"],
                "output_key": task["output_key"],
                "status": task_result["status"],
                "content": task_result["content"],
            })

            if task_result["status"] == "done":
                sections[task["output_key"]] = task_result["content"]
                accumulated_context += f"\n\n[Task {task['id']} – {task['title']}]:\n{task_result['content'][:500]}"
                logger.info(f"  ✓ Task {task['id']}: {task['title']}")
            else:
                logger.warning(f"  ✗ Task {task['id']}: {task['title']} – {task_result['error']}")

        # Generate overall summary
        completed_count = sum(1 for t in executed_tasks if t["status"] == "done")
        summary = (
            f"Completed {completed_count}/{len(tasks)} tasks. "
            f"Document type: {document_type}. "
            f"Sections generated: {list(sections.keys())}."
        )

        execution_data = {
            "summary": summary,
            "sections": sections,
            "document_type": document_type,
            "document_title": document_title,
            "assumptions": assumptions,
        }

        return executed_tasks, execution_data

    async def _execute_task(
        self,
        task: Dict,
        document_type: str,
        document_title: str,
        original_request: str,
        accumulated_context: str,
        assumptions: List[str],
    ) -> Dict[str, Any]:
        """
        Execute a single task with up to 2 retries, then fallback content.
        """
        assumptions_text = "\n".join(f"- {a}" for a in assumptions) if assumptions else "None"

        prompt = f"""You are producing content for a "{document_type}" titled: "{document_title}"

Original user request: {original_request}

Assumptions made for ambiguous parts:
{assumptions_text}

Context from previous tasks:
{accumulated_context if accumulated_context else "This is the first task."}

Current task to execute:
- Task #{task['id']}: {task['title']}
- Description: {task['description']}

Write the content for this task now. Be professional, specific, and use realistic mock data as needed."""

        for attempt in range(2):
            try:
                response = self.client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": EXECUTOR_SYSTEM},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.5,
                    max_tokens=700,
                )
                content = response.choices[0].message.content.strip()
                if len(content) < 20:
                    raise ValueError("Response too short")
                return {"status": "done", "content": content}

            except Exception as e:
                logger.warning(f"Task {task['id']} attempt {attempt+1} failed: {e}")
                if attempt == 1:
                    # Fallback: generate minimal placeholder content
                    fallback = (
                        f"**{task['title']}**\n\n"
                        f"[Content generation encountered an error. "
                        f"This section covers: {task['description']}. "
                        f"Please review and complete manually.]\n\n"
                        f"Key points to address:\n"
                        f"- Primary objective of this section\n"
                        f"- Supporting data and analysis\n"
                        f"- Conclusions and next steps"
                    )
                    return {"status": "done", "content": fallback, "error": str(e)}

        return {
            "status": "failed",
            "content": "",
            "error": "Max retries exceeded"
        }
