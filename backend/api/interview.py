"""模拟面试 API。

根据用户上传的简历，由 LLM 扮演面试官进行对话式面试。
支持：简历上传与解析、生成面试问题、对用户回答打分并给出参考答案、跳过问题查看答案。
"""
from __future__ import annotations

import json
import random
import time
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.deps import get_current_user
from backend.config import settings
from backend.database.models import User
from backend.database.session import get_db
from backend.services.resume_store import load_resume_data
from backend.services.resume_upload import upload_resume_file as process_resume_upload

router = APIRouter()


# ---------- 请求/响应模型 ----------

class ResumeContext(BaseModel):
    """简历上下文，用于面试问题生成。"""
    basic: dict[str, str] = Field(default_factory=dict)
    education: list[dict[str, str]] = Field(default_factory=list)
    skills: list[dict[str, str]] = Field(default_factory=list)
    projects: list[dict[str, str]] = Field(default_factory=list)
    target_position: str = Field(default="")
    intro_keywords: str = Field(default="")
    intro: str = Field(default="")


class StartInterviewRequest(BaseModel):
    """开始面试请求。"""
    resume: ResumeContext
    question_count: int = Field(default=8, description="面试问题数量")


class InterviewQuestion(BaseModel):
    """单个面试问题。"""
    index: int
    question: str
    category: str = Field(default="", description="问题分类，如技术/项目/行为等")


class StartInterviewResponse(BaseModel):
    """开始面试响应，返回所有问题。"""
    session_id: str
    questions: list[InterviewQuestion]


class AnswerRequest(BaseModel):
    """用户回答请求。"""
    session_id: str
    question_index: int
    question: str
    answer: str
    resume: ResumeContext


class AnswerResponse(BaseModel):
    """回答评分响应。"""
    score: int = Field(ge=1, le=10, description="评分 1-10")
    feedback: str = Field(default="", description="对用户回答的点评")
    reference_answer: str = Field(default="", description="参考答案")


class SkipRequest(BaseModel):
    """跳过问题请求。"""
    session_id: str
    question_index: int
    question: str
    resume: ResumeContext


class SkipResponse(BaseModel):
    """跳过问题响应，直接给出参考答案。"""
    reference_answer: str = Field(default="", description="参考答案")
    tips: str = Field(default="", description="回答建议")


# ---------- LLM 调用 ----------

def _init_llm(temperature: float = 0.7, max_tokens: int = 2000) -> Any:
    """初始化 DeepSeek LLM 客户端。"""
    if not settings.deepseek_api_key:
        return None
    try:
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as e:
        print(f"[InterviewAPI] LLM 初始化失败: {e}")
        return None


async def _call_llm(prompt: str, temperature: float = 0.7, max_tokens: int = 2000) -> str:
    """调用 LLM 并返回结果。"""
    llm = _init_llm(temperature, max_tokens)
    if llm is None:
        return ""
    try:
        response = await llm.ainvoke(prompt)
        return response.content
    except Exception as e:
        print(f"[InterviewAPI] LLM 调用失败: {e}")
        return ""


async def _stream_llm(prompt: str, temperature: float = 0.7, max_tokens: int = 2000):
    """流式调用 LLM，逐 token yield 字符串。"""
    llm = _init_llm(temperature, max_tokens)
    if llm is None:
        yield ""
        return
    try:
        async for chunk in llm.astream(prompt):
            if chunk.content:
                yield chunk.content
    except Exception as e:
        print(f"[InterviewAPI] LLM 流式调用失败: {e}")
        yield ""


def _build_resume_summary(resume: ResumeContext) -> str:
    """构建简历摘要文本。"""
    parts = []
    name = resume.basic.get("name", "")
    if name:
        parts.append(f"姓名：{name}")
    if resume.target_position:
        parts.append(f"目标职位：{resume.target_position}")
    if resume.education:
        for edu in resume.education:
            school = edu.get("school", "")
            major = edu.get("major", "")
            degree = edu.get("degree", "")
            if school:
                parts.append(f"教育：{school} · {major} · {degree}")
    if resume.skills:
        skill_strs = []
        for sg in resume.skills:
            cat = sg.get("category", "")
            items = sg.get("items", "")
            if cat or items:
                skill_strs.append(f"{cat}: {items}")
        if skill_strs:
            parts.append(f"技能：{'; '.join(skill_strs)}")
    if resume.projects:
        for p in resume.projects:
            pname = p.get("name", "")
            role = p.get("role", "")
            desc = p.get("description", "")
            tech = p.get("tech_stack", "")
            if pname:
                parts.append(f"项目：{pname} | 角色：{role} | 技术：{tech}\n描述：{desc}")
    if resume.intro:
        parts.append(f"自我介绍：{resume.intro}")
    elif resume.intro_keywords:
        parts.append(f"自我介绍关键词：{resume.intro_keywords}")
    return "\n".join(parts) if parts else "(无简历信息)"


def _build_questions_prompt(req: StartInterviewRequest) -> str:
    """构建生成面试问题的 Prompt。"""
    resume_summary = _build_resume_summary(req.resume)
    position = req.resume.target_position or "软件开发工程师"

    return f"""你是一位资深的技术面试官。请根据以下求职者的简历信息，生成 {req.question_count} 个面试问题。

要求：
1. 问题要针对简历中的技能、项目经历和教育背景进行深入提问
2. 问题类型要多样化，包括：
   - 技术基础题（考察基本功）
   - 项目深挖题（针对简历中的项目追问细节）
   - 场景设计题（实际工作中的技术方案）
   - 行为面试题（团队协作、解决问题等软技能）
3. 问题要有区分度，从易到难
4. 目标职位：{position}
5. 每个问题标注分类：tech（技术）、project（项目）、design（设计）、behavior（行为）

## 求职者简历
{resume_summary}

## 输出格式
请严格按以下 JSON 格式返回，不要包含其他内容：
{{
  "questions": [
    {{
      "index": 0,
      "question": "面试问题内容",
      "category": "tech"
    }}
  ]
}}"""


def _build_score_prompt(req: AnswerRequest) -> str:
    """构建回答评分 Prompt。"""
    resume_summary = _build_resume_summary(req.resume)
    position = req.resume.target_position or "软件开发工程师"

    return f"""你是一位资深的技术面试官。求职者正在面试 {position} 岗位。

## 求职者简历
{resume_summary}

## 面试问题
{req.question}

## 求职者的回答
{req.answer}

请你对该回答进行评分和点评：

1. **评分**：1-10 分（1=完全不会，10=非常优秀）
2. **点评**：指出回答的优缺点，哪些地方说得好，哪些需要改进
3. **参考答案**：给出一个高质量的参考答案，展示面试官期望的回答方式

## 输出格式
请严格按以下 JSON 格式返回，不要包含其他内容：
{{
  "score": 7,
  "feedback": "点评内容",
  "reference_answer": "参考答案内容"
}}"""


def _build_skip_prompt(req: SkipRequest) -> str:
    """构建跳过问题查看答案的 Prompt。"""
    resume_summary = _build_resume_summary(req.resume)
    position = req.resume.target_position or "软件开发工程师"

    return f"""你是一位资深的技术面试官。求职者正在面试 {position} 岗位，但选择了跳过此问题。

## 求职者简历
{resume_summary}

## 面试问题
{req.question}

请给出：
1. **参考答案**：一个高质量的参考答案
2. **回答建议**：回答这类问题的思路和技巧

## 输出格式
请严格按以下 JSON 格式返回，不要包含其他内容：
{{
  "reference_answer": "参考答案内容",
  "tips": "回答建议和思路"
}}"""


# ---------- 简历上传 & 读取 API ----------


@router.post("/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """上传简历文件（覆盖写，与个人中心 / 毕业季共用同一份简历）。"""
    filename = file.filename or "resume"
    content = await file.read()
    result = await process_resume_upload(db, current_user.id, filename, content)
    return JSONResponse(status_code=200, content=result)


@router.get("/resume")
async def get_resume(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """获取当前用户持久化的简历数据。"""
    data = load_resume_data(db, current_user.id)
    if data is None:
        return {"ok": False, "resume": None, "message": "尚未上传简历"}
    return {"ok": True, "resume": data}


# ---------- 面试 API ----------

@router.post("/start", response_model=StartInterviewResponse)
async def start_interview(req: StartInterviewRequest) -> StartInterviewResponse:
    """开始模拟面试，生成面试问题列表。"""
    session_id = f"iv_{int(time.time())}_{random.randint(1000, 9999)}"
    prompt = _build_questions_prompt(req)
    llm_result = await _call_llm(prompt)
    data = _parse_json(llm_result)

    if data and "questions" in data:
        questions = []
        for i, q in enumerate(data["questions"]):
            questions.append(InterviewQuestion(
                index=i,
                question=q.get("question", ""),
                category=q.get("category", "tech"),
            ))
        return StartInterviewResponse(session_id=session_id, questions=questions)

    # 降级：返回默认问题
    position = req.resume.target_position or "软件开发工程师"
    default_questions = [
        InterviewQuestion(index=0, question=f"请简单介绍一下你自己，以及为什么选择{position}方向？", category="behavior"),
        InterviewQuestion(index=1, question="请描述一个你遇到过的技术难题，你是如何解决的？", category="project"),
        InterviewQuestion(index=2, question="你对哪些技术栈比较熟悉？请选择一个深入聊聊。", category="tech"),
        InterviewQuestion(index=3, question="在团队协作中，你通常扮演什么角色？遇到过什么分歧吗？", category="behavior"),
        InterviewQuestion(index=4, question="请描述一个你最满意的项目，你的具体贡献是什么？", category="project"),
    ]
    return StartInterviewResponse(session_id=session_id, questions=default_questions)


@router.post("/answer", response_model=AnswerResponse)
async def submit_answer(req: AnswerRequest) -> AnswerResponse:
    """提交回答，获取评分和参考答案。"""
    prompt = _build_score_prompt(req)
    llm_result = await _call_llm(prompt)
    data = _parse_json(llm_result)

    if data:
        return AnswerResponse(
            score=max(1, min(10, data.get("score", 5))),
            feedback=data.get("feedback", ""),
            reference_answer=data.get("reference_answer", ""),
        )

    return AnswerResponse(
        score=5,
        feedback="评分服务暂时不可用",
        reference_answer="参考答案生成失败，请稍后重试",
    )


@router.post("/skip", response_model=SkipResponse)
async def skip_question(req: SkipRequest) -> SkipResponse:
    """跳过问题，查看参考答案。"""
    prompt = _build_skip_prompt(req)
    llm_result = await _call_llm(prompt)
    data = _parse_json(llm_result)

    if data:
        return SkipResponse(
            reference_answer=data.get("reference_answer", ""),
            tips=data.get("tips", ""),
        )

    return SkipResponse(
        reference_answer="参考答案生成失败，请稍后重试",
        tips="建议结合自身经验组织回答",
    )


# ---------- 流式面试 API ----------

@router.post("/answer/stream")
async def submit_answer_stream(req: AnswerRequest) -> StreamingResponse:
    """提交回答，流式返回评分和参考答案（SSE）。

    事件序列：
      1. token — 逐 token 返回 LLM 原始输出
      2. result — 解析后的结构化结果 {score, feedback, reference_answer}
      3. done  — 完成
    """
    prompt = _build_score_prompt(req)

    async def event_generator():
        full_text = ""
        async for token in _stream_llm(prompt):
            if token:
                full_text += token
                yield f'data: {json.dumps({"type": "token", "content": token}, ensure_ascii=False)}\n\n'

        # 解析完整结果
        data = _parse_json(full_text)
        if data:
            result = {
                "type": "result",
                "score": max(1, min(10, data.get("score", 5))),
                "feedback": data.get("feedback", ""),
                "reference_answer": data.get("reference_answer", ""),
            }
        else:
            result = {
                "type": "result",
                "score": 5,
                "feedback": "评分服务暂时不可用",
                "reference_answer": "参考答案生成失败，请稍后重试",
            }
        yield f'data: {json.dumps(result, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/skip/stream")
async def skip_question_stream(req: SkipRequest) -> StreamingResponse:
    """跳过问题，流式返回参考答案（SSE）。

    事件序列：
      1. token — 逐 token 返回 LLM 原始输出
      2. result — 解析后的结构化结果 {reference_answer, tips}
      3. done  — 完成
    """
    prompt = _build_skip_prompt(req)

    async def event_generator():
        full_text = ""
        async for token in _stream_llm(prompt):
            if token:
                full_text += token
                yield f'data: {json.dumps({"type": "token", "content": token}, ensure_ascii=False)}\n\n'

        data = _parse_json(full_text)
        if data:
            result = {
                "type": "result",
                "reference_answer": data.get("reference_answer", ""),
                "tips": data.get("tips", ""),
            }
        else:
            result = {
                "type": "result",
                "reference_answer": "参考答案生成失败，请稍后重试",
                "tips": "建议结合自身经验组织回答",
            }
        yield f'data: {json.dumps(result, ensure_ascii=False)}\n\n'
        yield f'data: {json.dumps({"type": "done"}, ensure_ascii=False)}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
