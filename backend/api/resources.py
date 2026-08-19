"""资源查询 API。

提供专业、机构、联系方式、服务入口、下载资料、学术搜索等结构化数据查询。
数据源：metadata JSON 文件（由 crawler 模块采集生成）+ 第三方 API。
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.agents.answer_generator import AnswerGenerator
from backend.tools.academic_search_tool import AcademicSearchTool
from backend.tools.contact_tool import ContactTool
from backend.tools.download_tool import DownloadTool
from backend.tools.job_tool import JobDataError, JobTool
from backend.tools.major_tool import MajorTool
from backend.tools.service_link_tool import ServiceLinkTool

router = APIRouter()

# 全局工具单例（避免每次请求重建）
_major_tool = MajorTool()
_download_tool = DownloadTool()
_job_tool = JobTool()
_contact_tool = ContactTool()
_service_link_tool = ServiceLinkTool()
_academic_search_tool = AcademicSearchTool()
_answer_generator = AnswerGenerator()


class MajorItem(BaseModel):
    major_code: str | None = None
    major_name: str
    college_name: str | None = None
    discipline_category: str | None = None
    degree_category: str | None = None
    training_plan_url: str | None = None
    source_url: str | None = None


class OrganizationItem(BaseModel):
    name: str
    type: str | None = None
    website_url: str | None = None
    parent_name: str | None = None
    source_url: str | None = None


class ContactItem(BaseModel):
    department: str
    office_name: str | None = None
    campus: str | None = None
    service_scope: str | None = None
    phone: str | None = None
    address: str | None = None
    source_url: str | None = None


class ServiceLinkItem(BaseModel):
    name: str
    category: str | None = None
    url: str
    requires_login: bool = False
    user_role: str | None = None
    description: str | None = None
    department: str | None = None


class DownloadResourceItem(BaseModel):
    title: str
    category: str | None = None
    audience: str | None = None
    file_type: str | None = None
    source_page_url: str
    file_url: str | None = None
    publish_date: str | None = None
    department: str | None = None


class JobItem(BaseModel):
    id: str
    kind: Literal["posting", "fair"]
    title: str
    company: str | None = None
    published: str | None = None
    time: str | None = None
    salary: str | None = None
    education: str | None = None
    industry: str | None = None
    location: str | None = None
    url: str


class JobListResponse(BaseModel):
    total: int
    items: list[JobItem]


class ListResponse(BaseModel):
    total: int
    items: list
    facets: dict[str, list[str]] | None = None
    llm_query_optimization: dict | None = Field(
        default=None, description="LLM 关键词优化结果（学术搜索专用）"
    )


def _detect_file_type(url: str) -> str | None:
    """根据 URL 后缀推断文件类型。"""
    if not url:
        return None
    lower = url.lower().split("?")[0]
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".doc"):
        return "doc"
    if lower.endswith(".docx"):
        return "docx"
    if lower.endswith(".xls"):
        return "xls"
    if lower.endswith(".xlsx"):
        return "xlsx"
    if lower.endswith((".htm", ".html")):
        return "page"
    return None


def _detect_campus(text: str) -> str | None:
    """从文本中推断校区。"""
    if "海珠" in text:
        return "海珠"
    if "白云" in text:
        return "白云"
    return None


@router.get("/majors", response_model=ListResponse)
async def list_majors(
    keyword: str | None = Query(default=None, description="专业名或代码关键词"),
    college: str | None = Query(default=None, description="所属学院"),
    top_k: int = Query(default=20, ge=1, le=100),
) -> ListResponse:
    """本科专业查询。"""
    # 无过滤参数时传空串，工具会返回全部
    query = ""
    if keyword:
        query = keyword
    elif college:
        query = college
    result = await _major_tool.run(query, top_k=top_k)
    items: list[dict[str, Any]] = []
    for item in result.get("items", []):
        items.append(
            {
                "major_name": item.get("title", ""),
                "college_name": item.get("department"),
                "training_plan_url": item.get("file_url"),
                "source_url": item.get("source_page_url"),
            }
        )
    return ListResponse(total=len(items), items=items)


@router.get("/organizations", response_model=ListResponse)
async def list_organizations(
    type: str | None = Query(default=None, description="机构类型：教学机构/党政管理机构/教辅科研机构/服务平台"),
    top_k: int = Query(default=50, ge=1, le=200),
) -> ListResponse:
    """机构学院查询。"""
    # 复用 major_tool 查询教学机构（其覆盖机构设置 metadata）
    result = await _major_tool.run("学院 机构 教学", top_k=top_k)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in result.get("items", []):
        name = item.get("title", "")
        if not name or name in seen:
            continue
        seen.add(name)
        items.append(
            {
                "name": name,
                "type": "教学机构",
                "source_url": item.get("source_page_url"),
            }
        )
    return ListResponse(total=len(items), items=items)


@router.get("/contacts", response_model=ListResponse)
async def list_contacts(
    department: str | None = Query(default=None, description="部门关键词"),
    campus: str | None = Query(default=None, description="校区：白云/海珠"),
    top_k: int = Query(default=20, ge=1, le=100),
) -> ListResponse:
    """联系方式查询。"""
    query = ""
    if department:
        query = department
    elif campus:
        query = campus
    result = await _contact_tool.run(query, top_k=top_k)
    items: list[dict[str, Any]] = []
    for item in result.get("items", []):
        title = item.get("title", "")
        # campus 过滤
        if campus:
            item_campus = _detect_campus(title) or _detect_campus(item.get("phone", ""))
            if item_campus != campus:
                continue
        items.append(
            {
                "department": item.get("department", ""),
                "office_name": title,
                "service_scope": title,
                "phone": item.get("phone"),
                "address": item.get("address"),
                "source_url": item.get("source_page_url"),
            }
        )
    return ListResponse(total=len(items), items=items)


@router.get("/service-links", response_model=ListResponse)
async def list_service_links(
    category: str | None = Query(default=None, description="服务分类：教务/科研/行政/后勤/网络/医疗/招采/就业"),
    user_role: str | None = Query(default=None, description="用户角色"),
    top_k: int = Query(default=30, ge=1, le=100),
) -> ListResponse:
    """服务入口查询。"""
    query = category or ""
    result = await _service_link_tool.run(query, top_k=top_k)
    items: list[dict[str, Any]] = []
    for item in result.get("items", []):
        items.append(
            {
                "name": item.get("title", ""),
                "url": item.get("url", ""),
                "department": item.get("department"),
                "category": category,
            }
        )
    return ListResponse(total=len(items), items=items)


@router.get("/downloads", response_model=ListResponse)
async def list_downloads(
    keyword: str | None = Query(default=None, description="资料关键词"),
    category: str | None = Query(default=None, description="真实 metadata 分类，使用响应 facets 中的值"),
    audience: str | None = Query(default=None, description="真实 metadata 适用对象，使用响应 facets 中的值"),
    top_k: int = Query(default=20, ge=1, le=100),
) -> ListResponse:
    """资料下载查询。"""
    result = await _download_tool.run(
        keyword or "",
        category=category,
        audience=audience,
        top_k=top_k,
    )
    items: list[dict[str, Any]] = []
    for item in result.get("items", []):
        file_url = item.get("file_url", "")
        items.append(
            {
                "title": item.get("title", ""),
                "category": item.get("category") or None,
                "audience": item.get("audience") or None,
                "file_type": item.get("file_type") or _detect_file_type(file_url),
                "source_page_url": item.get("source_page_url", ""),
                "file_url": file_url or None,
                "publish_date": item.get("publish_date") or None,
                "department": item.get("department") or None,
            }
        )
    return ListResponse(
        total=int(result.get("total", len(items))),
        items=items,
        facets=result.get("facets"),
    )


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    kind: Literal["posting", "fair"] = Query(default="posting"),
    keyword: str | None = Query(default=None),
    company: str | None = Query(default=None),
    top_k: int = Query(default=50, ge=1, le=100),
) -> JobListResponse:
    """查询公开职位或校园招聘活动。"""
    try:
        result = await _job_tool.run(
            keyword or "", kind=kind, company=company, top_k=top_k
        )
    except JobDataError as error:
        raise HTTPException(status_code=503, detail="就业数据暂不可用") from error
    return JobListResponse(total=result["total"], items=result["items"])


@router.get("/academic", response_model=ListResponse)
async def search_academic(
    keyword: str = Query(default=..., description="搜索关键词"),
    top_k: int = Query(default=5, ge=1, le=20),
) -> ListResponse:
    """学术论文搜索（LLM 优化关键词 + Crossref/arXiv API）。

    流程：用户输入 → LLM 优化为学术搜索关键词 → Crossref + arXiv 搜索 → 返回结果
    """
    result = await _academic_search_tool.run(keyword, top_k=top_k)
    items: list[dict[str, Any]] = []
    for item in result.get("items", []):
        items.append(
            {
                "title": item.get("title", ""),
                "authors": item.get("authors", ""),
                "year": item.get("year", ""),
                "doi": item.get("doi", ""),
                "cited": item.get("cited", 0),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "snippet": item.get("snippet", ""),
            }
        )
    # 附加 LLM 优化关键词信息
    extra = {}
    query_used = result.get("query_used")
    if query_used:
        extra["llm_query_optimization"] = query_used
    return ListResponse(total=len(items), items=items, **extra)


class AcademicAnalyzeRequest(BaseModel):
    """学术搜索 AI 解读请求。"""
    keyword: str = Field(..., description="搜索关键词")
    papers: list[dict[str, Any]] = Field(..., description="搜索结果论文列表")


@router.get("/academic/optimize")
async def optimize_academic_query(
    keyword: str = Query(default=..., description="用户输入的自然语言查询"),
) -> dict[str, Any]:
    """LLM 优化学术搜索关键词。

    将用户自然语言问题转化为 Crossref/arXiv 友好的搜索关键词。
    """
    zh_kw, en_kw = await _academic_search_tool.optimize_query(keyword)
    return {
        "original": keyword,
        "zh_keywords": zh_kw,
        "en_keywords": en_kw,
    }


@router.post("/academic/analyze")
async def analyze_academic(req: AcademicAnalyzeRequest):
    """AI 解读学术搜索结果。

    将搜索到的论文列表发送给 LLM，生成研究脉络梳理和推荐分析。
    """
    if _answer_generator.llm is None:
        return {"analysis": "(LLM 未初始化，请检查 DEEPSEEK_API_KEY 配置)"}

    # 构建论文摘要文本
    papers_text = ""
    for i, p in enumerate(req.papers[:10], 1):
        papers_text += f"{i}. {p.get('title', '')}\n"
        if p.get("authors"):
            papers_text += f"   作者：{p['authors']}\n"
        if p.get("year"):
            papers_text += f"   年份：{p['year']}\n"
        if p.get("cited"):
            papers_text += f"   被引用：{p['cited']} 次\n"
        if p.get("snippet"):
            papers_text += f"   摘要：{p['snippet']}\n"
        if p.get("doi"):
            papers_text += f"   DOI：{p['doi']}\n"
        papers_text += "\n"

    prompt = f"""你是一位学术研究助手，请对以下关于「{req.keyword}」的搜索结果进行解读分析。

要求：
1. 用中文回答，语言简洁专业
2. 梳理该领域的研究脉络和主要方向
3. 标注高引用经典论文和前沿趋势
4. 为本科生/研究生推荐最值得阅读的 2-3 篇论文，并说明推荐理由
5. 提供进一步研究的建议方向

【搜索结果】
{papers_text}

【AI 解读】
"""
    try:
        response = await _answer_generator.llm.ainvoke(prompt)
        return {"analysis": response.content}
    except Exception as e:
        return {"analysis": f"(AI 解读失败: {e})"}
