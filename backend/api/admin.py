"""管理后台 API。

用于知识库重建、链接检测、采集任务触发、日志查看。
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class RebuildRequest(BaseModel):
    """知识库重建请求。"""

    force: bool = False


class TaskResponse(BaseModel):
    """任务响应。"""

    task_id: str
    status: str
    message: str


@router.post("/kb/rebuild", response_model=TaskResponse)
async def rebuild_kb(req: RebuildRequest) -> TaskResponse:
    """重建向量知识库。"""
    # TODO: 触发 crawler.build_kb
    return TaskResponse(task_id="stub", status="pending", message="知识库重建任务已提交")


@router.get("/links/check", response_model=TaskResponse)
async def check_links() -> TaskResponse:
    """检测来源 URL 有效性。"""
    # TODO: 触发链接检测脚本
    return TaskResponse(task_id="stub", status="pending", message="链接检测任务已提交")


@router.post("/crawl/run", response_model=TaskResponse)
async def run_crawler() -> TaskResponse:
    """手动触发官网采集。"""
    # TODO: 触发 crawler
    return TaskResponse(task_id="stub", status="pending", message="采集任务已提交")
