"""Run the user's two questions without writing chat history or QA cache."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from backend.agents.controller import AgentController
from backend.config import settings


async def main():
    # Process-local validation settings: exactly two answer calls, no planner,
    # judge or SDK retries. The running app's configuration is not changed.
    settings.query_planner_mode = "rule_fallback"
    settings.rag_evidence_judge_enabled = False
    settings.deepseek_max_retries = 0
    controller = AgentController()
    actual_llm = controller.answer_generator.llm

    class BudgetedLLM:
        calls = 0

        async def ainvoke(self, prompt):
            if self.calls >= 2:
                raise RuntimeError("Validation is limited to two API calls")
            self.calls += 1
            response = await actual_llm.ainvoke(prompt)
            print(json.dumps({"answer_call": self.calls, "usage": getattr(response, "usage_metadata", None)}), flush=True)
            return response

    controller.answer_generator.llm = BudgetedLLM()
    for question in ["我是信计大三的学生，本学年我需要修什么课程", "信计需要修的学分是多少，有哪些课程"]:
        result = await controller.handle(question, user_id=2, knowledge_scope="with_personal", has_personal_documents=True)
        summary = result.get("retrieval_summary", {})
        record = {
            "question": question, "answer": result.get("answer"),
            "fallback": result.get("fallback"),
            "sources": [{k: source.get(k) for k in ("title", "doc_id", "citation_id")} for source in result.get("sources", [])],
            "personal_status": summary.get("personal_documents_status"),
            "selection": summary.get("evidence_selection"),
        }
        print(json.dumps(record, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
