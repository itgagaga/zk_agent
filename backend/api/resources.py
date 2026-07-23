"""资源查询 API。

提供专业、机构、联系方式、服务入口、下载资料等结构化数据查询。
数据源：metadata JSON 文件（由 crawler 模块采集生成）。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from backend.tools.contact_tool import ContactTool
from backend.tools.download_tool import DownloadTool
from backend.tools.major_tool import MajorTool
from backend.tools.service_link_tool import ServiceLinkTool

router = APIRouter()

# 全局工具单例（避免每次请求重建）
_major_tool = MajorTool()
_download_tool = DownloadTool()
_contact_tool = ContactTool()
_service_link_tool = ServiceLinkTool()


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


class ListResponse(BaseModel):
    total: int
    items: list


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
    category: str | None = Query(default=None, description="分类：学生下载/学籍学位/考务/教材/培养方案/研究生培养"),
    audience: str | None = Query(default=None, description="适用对象：学生/教师/教务人员"),
    top_k: int = Query(default=20, ge=1, le=100),
) -> ListResponse:
    """资料下载查询。"""
    query = keyword or category or ""
    result = await _download_tool.run(query, top_k=top_k)
    items: list[dict[str, Any]] = []
    for item in result.get("items", []):
        file_url = item.get("file_url", "")
        items.append(
            {
                "title": item.get("title", ""),
                "category": category,
                "audience": audience or "学生",
                "file_type": _detect_file_type(file_url),
                "source_page_url": item.get("source_page_url", ""),
                "file_url": file_url,
                "publish_date": item.get("publish_date"),
                "department": item.get("department"),
            }
        )
    return ListResponse(total=len(items), items=items)
