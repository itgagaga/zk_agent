"""简历增强 API。

接收用户填写的简历信息，调用 LLM 对自我介绍、专业技能、
项目经历等内容进行扩展优化，返回增强后的简历数据。
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.auth.deps import get_current_user, get_current_user_optional
from backend.config import settings
from backend.database.models import User
from backend.database.session import get_db
from backend.services.resume_store import load_resume_data, save_resume_data
from backend.services.resume_upload import upload_resume_file as process_resume_upload
from backend.utils.llm_content import extract_text_content

router = APIRouter()


# ---------- 请求/响应模型 ----------

class EducationItem(BaseModel):
    school: str = ""
    major: str = ""
    degree: str = ""
    start: str = ""
    end: str = ""


class SkillGroup(BaseModel):
    category: str = ""
    items: str = ""  # 逗号分隔的技能列表


class ProjectItem(BaseModel):
    name: str = ""
    role: str = ""
    start: str = ""
    end: str = ""
    description: str = ""
    tech_stack: str = ""


class ResumeEnhanceRequest(BaseModel):
    intro_keywords: str = Field(default="", description="自我介绍关键词/短句")
    skills: list[SkillGroup] = Field(default_factory=list, description="专业技能分组")
    projects: list[ProjectItem] = Field(default_factory=list, description="项目经历")
    target_position: str = Field(default="", description="目标职位")
    basic: dict[str, str] = Field(default_factory=dict, description="基本情况，如 name/phone/email 等")
    education: list[EducationItem] = Field(default_factory=list, description="教育背景")


class ResumeEnhanceResponse(BaseModel):
    intro: str = Field(default="", description="LLM 扩展后的自我介绍")
    skills: list[SkillGroup] = Field(default_factory=list, description="润色后的专业技能")
    projects: list[ProjectItem] = Field(default_factory=list, description="优化后的项目经历")


# ---------- LLM 调用 ----------

def _init_llm() -> Any:
    """初始化 DeepSeek LLM 客户端。"""
    if not settings.deepseek_api_key:
        return None
    try:
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=0.5,
            max_tokens=2000,
        )
    except Exception as e:
        print(f"[ResumeAPI] LLM 初始化失败: {e}")
        return None


def _build_enhance_prompt(req: ResumeEnhanceRequest) -> str:
    """构建简历增强 Prompt。"""
    parts = []

    # 基本信息
    name = req.basic.get("name", "")
    phone = req.basic.get("phone", "")
    email = req.basic.get("email", "")

    context_lines = []
    if name:
        context_lines.append(f"姓名：{name}")
    if req.target_position:
        context_lines.append(f"目标职位：{req.target_position}")

    # 教育背景
    if req.education:
        context_lines.append("\n教育背景：")
        for edu in req.education:
            if edu.school:
                context_lines.append(f"- {edu.school} · {edu.major} · {edu.degree} ({edu.start}-{edu.end})")

    # 专业技能
    if req.skills:
        context_lines.append("\n专业技能（需润色）：")
        for sg in req.skills:
            if sg.category or sg.items:
                context_lines.append(f"- {sg.category}: {sg.items}")

    # 项目经历
    if req.projects:
        context_lines.append("\n项目经历（需优化描述）：")
        for p in req.projects:
            if p.name:
                context_lines.append(
                    f"- {p.name} | {p.role} | {p.start}-{p.end}\n"
                    f"  描述：{p.description}\n"
                    f"  技术栈：{p.tech_stack}"
                )

    context = "\n".join(context_lines) if context_lines else "(无额外上下文)"

    prompt = f"""你是一位专业的简历顾问。请根据以下用户信息，完成三项任务。

重要规则：
- 如果用户没有提供某个模块的内容（为空或缺失），请根据目标职位和已有信息，**自动生成合理的默认内容**。
- 专业技能、项目经历、自我介绍这三个模块最适合优化，即使只给了很少的信息也要生成完整内容。
- 不要留空，每个模块都必须有输出。

## 任务一：撰写自我介绍
根据用户给出的关键词/短句，撰写一段150-250字的自我介绍。
要求：语言精炼、突出亮点、体现个人优势，不要使用空洞套话。
{"目标职位为「" + req.target_position + "」，请针对该职位方向撰写。" if req.target_position else ""}
如果用户未提供关键词，请根据其他信息（专业、技能、项目等）自动概括。

用户给出的自我介绍关键词：
{req.intro_keywords or "(用户未提供，请根据其他信息自动生成)"}

## 任务二：润色/生成专业技能
对用户给出的技能列表进行整理和润色：
1. 使用行业标准术语
2. 合理分类，去掉重复项
3. 每个分类下按重要性排序
如果用户未提供任何技能，请根据目标职位自动生成3-4个分类的合理技能。
{"目标职位为「" + req.target_position + "」" if req.target_position else "请假设为计算机相关专业应届毕业生"}

## 任务三：优化/生成项目经历
对每个项目经历进行优化：
1. 使用STAR法则（情境-任务-行动-结果）优化描述
2. 使描述更专业、更有量化感
3. 每条描述控制在50字以内，给出2-4条要点
如果用户未提供任何项目，请根据目标职位自动生成1-2个合理的模拟项目经历。
{"目标职位为「" + req.target_position + "」" if req.target_position else ""}

## 上下文信息
{context}

## 输出格式
请严格按以下 JSON 格式返回，不要包含其他内容：
{{
  "intro": "自我介绍全文",
  "skills": [
    {{"category": "分类名", "items": "技能1, 技能2, 技能3"}}
  ],
  "projects": [
    {{
      "name": "项目名",
      "role": "角色",
      "start": "开始时间",
      "end": "结束时间",
      "description": "优化后的项目描述，用分号分隔多个要点",
      "tech_stack": "技术栈"
    }}
  ]
}}"""
    return prompt


async def _call_llm(prompt: str) -> str:
    """调用 LLM 并返回结果。"""
    llm = _init_llm()
    if llm is None:
        return ""
    try:
        response = await llm.ainvoke(prompt)
        return extract_text_content(response)
    except Exception as e:
        print(f"[ResumeAPI] LLM 调用失败: {e}")
        return ""


def _parse_llm_response(text: str, req: ResumeEnhanceRequest) -> ResumeEnhanceResponse:
    """解析 LLM 返回的 JSON，解析失败则回退到原始数据。"""
    if not text:
        return ResumeEnhanceResponse(
            intro=req.intro_keywords,
            skills=req.skills,
            projects=req.projects,
        )

    # 尝试从返回文本中提取 JSON
    json_str = text
    if "```json" in text:
        json_str = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        json_str = text.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(json_str)
        return ResumeEnhanceResponse(
            intro=data.get("intro", req.intro_keywords),
            skills=[SkillGroup(**s) for s in data.get("skills", req.skills)],
            projects=[ProjectItem(**p) for p in data.get("projects", req.projects)],
        )
    except (json.JSONDecodeError, TypeError):
        # 解析失败，回退
        return ResumeEnhanceResponse(
            intro=req.intro_keywords,
            skills=req.skills,
            projects=req.projects,
        )


# ---------- API 端点 ----------


class ResumeProfileResponse(BaseModel):
    ok: bool = True
    resume: dict[str, Any] | None = None
    message: str = ""


@router.get("/profile", response_model=ResumeProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeProfileResponse:
    """获取当前用户简历。"""
    data = load_resume_data(db, current_user.id)
    if data is None:
        return ResumeProfileResponse(ok=False, resume=None, message="尚未保存简历")
    return ResumeProfileResponse(ok=True, resume=data)


@router.put("/profile", response_model=ResumeProfileResponse)
async def put_profile(
    body: dict[str, Any],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeProfileResponse:
    """保存/更新当前用户简历 JSON。"""
    save_resume_data(db, current_user.id, body)
    return ResumeProfileResponse(ok=True, resume=body, message="已保存")


@router.post("/upload")
async def upload_resume_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """上传简历文件（覆盖写，与个人中心 / 模拟面试共用同一份简历）。"""
    filename = file.filename or "resume"
    content = await file.read()
    result = await process_resume_upload(db, current_user.id, filename, content)
    return JSONResponse(status_code=200, content=result)


@router.post("/enhance", response_model=ResumeEnhanceResponse)
async def enhance_resume(
    req: ResumeEnhanceRequest,
    current_user: User | None = Depends(get_current_user_optional),
) -> ResumeEnhanceResponse:
    """简历增强接口。

    接收用户填写的简历信息，调用 LLM 对自我介绍、专业技能、
    项目经历等内容进行扩展优化。
    """
    _ = current_user  # 登录用户可选，便于后续按账号统计
    prompt = _build_enhance_prompt(req)
    llm_result = await _call_llm(prompt)
    return _parse_llm_response(llm_result, req)
