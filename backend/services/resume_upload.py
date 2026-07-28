"""简历文件上传与解析（个人中心 / 毕业季 / 模拟面试共用，覆盖写）。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.config import settings
from backend.services.resume_store import save_resume_data
from backend.storage.user_files import delete_path, to_data_relative, user_resume_dir

ALLOWED_RESUME_EXT = {".pdf", ".docx", ".txt", ".md"}
MAX_RESUME_SIZE = 10 * 1024 * 1024  # 10MB


def _init_llm(temperature: float = 0.3, max_tokens: int = 2000) -> Any:
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
        print(f"[ResumeUpload] LLM 初始化失败: {e}")
        return None


async def _call_llm(prompt: str, temperature: float = 0.3, max_tokens: int = 2000) -> str:
    llm = _init_llm(temperature, max_tokens)
    if llm is None:
        return ""
    try:
        response = await llm.ainvoke(prompt)
        return response.content
    except Exception as e:
        print(f"[ResumeUpload] LLM 调用失败: {e}")
        return ""


def _build_parse_resume_prompt(resume_text: str) -> str:
    text = resume_text[:6000] if len(resume_text) > 6000 else resume_text
    return f"""请从以下简历文本中提取结构化信息。

## 简历原文
{text}

## 提取要求
1. 提取基本信息（姓名、手机、邮箱、地址等）
2. 提取教育背景
3. 提取专业技能，按分类整理
4. 提取项目经历，包括项目名、角色、描述、技术栈
5. 推断目标职位（如果简历中没有明确写出，请根据专业和技能推断）
6. 生成简短的自我介绍关键词

## 输出格式
请严格按以下 JSON 格式返回，不要包含其他内容：
{{
  "basic": {{
    "name": "姓名",
    "phone": "手机号",
    "email": "邮箱",
    "address": "地址"
  }},
  "education": [
    {{
      "school": "学校名",
      "major": "专业",
      "degree": "学历",
      "start": "开始时间",
      "end": "结束时间"
    }}
  ],
  "skills": [
    {{
      "category": "分类名",
      "items": "技能1, 技能2, 技能3"
    }}
  ],
  "projects": [
    {{
      "name": "项目名",
      "role": "角色",
      "start": "开始时间",
      "end": "结束时间",
      "description": "项目描述",
      "tech_stack": "技术栈"
    }}
  ],
  "target_position": "目标职位",
  "intro_keywords": "关键词1；关键词2；关键词3"
}}"""


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    json_str = text
    if "```json" in text:
        json_str = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        json_str = text.split("```")[1].split("```")[0].strip()
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None


async def upload_resume_file(
    db: Session,
    user_id: int,
    filename: str,
    content: bytes,
) -> dict[str, Any]:
    """解析并保存简历文件；重新上传覆盖该用户之前的简历。"""
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_RESUME_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {suffix}，仅支持 {', '.join(sorted(ALLOWED_RESUME_EXT))}",
        )
    if len(content) > MAX_RESUME_SIZE:
        raise HTTPException(status_code=400, detail="文件超过 10MB 限制")
    if not content:
        raise HTTPException(status_code=400, detail="文件为空")

    resume_dir = user_resume_dir(user_id)
    for old in resume_dir.glob("resume_file*"):
        delete_path(old)
    raw_path = resume_dir / f"resume_file{suffix}"
    raw_path.write_bytes(content)

    try:
        from crawler.parse_documents import parse_file

        parsed = parse_file(raw_path)
    except Exception as e:
        delete_path(raw_path)
        raise HTTPException(status_code=422, detail=f"文件解析失败: {e}") from e

    resume_text = parsed.get("full_text", "").strip()
    if not resume_text:
        delete_path(raw_path)
        raise HTTPException(status_code=422, detail="文件解析后文本为空")

    prompt = _build_parse_resume_prompt(resume_text)
    llm_result = await _call_llm(prompt, temperature=0.3, max_tokens=2000)
    data = _parse_json(llm_result)
    rel = to_data_relative(raw_path)
    upload_time = time.strftime("%Y-%m-%d %H:%M:%S")

    if data:
        data.setdefault("basic", {})
        data.setdefault("education", [])
        data.setdefault("skills", [])
        data.setdefault("projects", [])
        data.setdefault("target_position", "")
        data.setdefault("intro_keywords", "")
        data["raw_text"] = resume_text
        data["filename"] = filename
        data["upload_time"] = upload_time
        save_resume_data(db, user_id, data, file_path=rel)
        return {
            "ok": True,
            "filename": filename,
            "resume": data,
            "message": "简历上传并解析成功",
        }

    fallback = {
        "basic": {},
        "education": [],
        "skills": [],
        "projects": [],
        "target_position": "",
        "intro_keywords": "",
        "raw_text": resume_text,
        "filename": filename,
        "upload_time": upload_time,
    }
    save_resume_data(db, user_id, fallback, file_path=rel)
    return {
        "ok": True,
        "filename": filename,
        "resume": fallback,
        "message": "简历已上传，但 AI 结构化解析失败，已保存原始文本",
    }
