"""公开职位和校园招聘活动查询工具。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR
from backend.tools.base import BaseTool


class JobDataError(RuntimeError):
    """就业聚合 metadata 不可读取或结构不合法。"""


class JobTool(BaseTool):
    """从就业指导中心聚合 JSON 查询职位和招聘活动。"""

    name = "job_search"
    description = "查询公开职位和校园招聘活动"

    @staticmethod
    def _path(kind: str) -> Path:
        filenames = {"posting": "job_postings.json", "fair": "job_fairs.json"}
        if kind not in filenames:
            raise ValueError(f"unsupported job kind: {kind}")
        return DATA_DIR / "metadata" / "job" / filenames[kind]

    def _load_items(self, kind: str) -> list[dict[str, Any]]:
        path = self._path(kind)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise JobDataError(f"无法读取就业数据 {path}: {error}") from error
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise JobDataError(f"就业数据缺少 items 列表: {path}")
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _normalise(item: dict[str, Any], kind: str) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "kind": kind,
            "title": item.get("name") or "",
            "company": item.get("company") or "",
            "published": item.get("published") or "",
            "time": item.get("time") or "",
            "salary": item.get("salary") or "",
            "education": item.get("education") or "",
            "industry": item.get("industry") or "",
            "location": item.get("location") or "",
            "url": item.get("url") or "",
        }

    async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
        kind = kwargs.get("kind", "posting")
        company = str(kwargs.get("company") or "").strip().lower()
        top_k = int(kwargs.get("top_k", 50))
        keyword = question.strip().lower()

        candidates: list[dict[str, Any]] = []
        for raw in self._load_items(kind):
            url = str(raw.get("url") or "")
            if raw.get("status") not in {"downloaded", "discovered"}:
                continue
            if not url.startswith(("http://", "https://")):
                continue
            item = self._normalise(raw, kind)
            search_text = " ".join(
                str(item[key])
                for key in ("title", "company", "industry", "location")
            ).lower()
            if keyword and keyword not in search_text:
                continue
            if company and company not in item["company"].lower():
                continue
            candidates.append(item)

        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in candidates:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            unique.append(item)

        return {
            "tool": self.name,
            "items": unique[:top_k],
            "total": len(unique),
        }
