"""为采集资料生成稳定的功能分类、受众和文档类型标签。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


SOURCE_CATEGORIES = {
    "zhku_main": ("学校概况与机构设置", "学校信息"),
    "jwc": ("教学与教务", "教务资料"),
    "yjs": ("研究生教育与招生", "研究生资料"),
    "zsb": ("本科招生", "招生资料"),
    "xsc": ("学生事务", "学生服务"),
    "cwc": ("财务与报销", "财务资料"),
    "hqyzc": ("后勤服务", "后勤联系与办事"),
    "wlzx": ("网络与信息化", "信息化服务"),
    "xys": ("校医院服务", "医疗服务"),
    "job": ("就业与招聘", "就业资料"),
}

KNOWN_SOURCE_KEYS = set(SOURCE_CATEGORIES)
CATEGORY_ALIASES = {
    "学校主站": "学校概况与机构设置",
}


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        value = str(value).strip()
        if value and value not in result:
            result.append(value)
    return result


def _source_key(source_dir: str, filename: str) -> str:
    if source_dir in KNOWN_SOURCE_KEYS:
        return source_dir
    stem = Path(filename).stem
    prefix = stem.split("_", 1)[0]
    return prefix if prefix in KNOWN_SOURCE_KEYS else source_dir


def _text(meta: dict[str, Any], filename: str) -> str:
    return " ".join(
        str(meta.get(key, ""))
        for key in ("title", "summary", "source_url", "url", "name")
    ) + " " + filename


def _subcategory(source: str, text: str, default: str) -> str:
    if source == "jwc":
        if any(token in text for token in ("学生下载", "学生资料", "xsxz")):
            return "学生事务"
        if "专业目录" in text:
            return "专业目录"
        if "培养方案" in text:
            return "培养方案"
    if source == "yjs":
        if any(token in text for token in ("下载", "资料", "download")):
            return "研究生资料下载"
        if any(token in text for token in ("招生", "章程", "复试", "调剂")):
            return "研究生招生"
    if source == "job":
        if any(
            token in text for token in ("job_fairs", "event_", "宣讲会", "招聘会")
        ):
            return "校园招聘活动"
        if "job_postings" in text or "job_" in text or "职位" in text:
            return "公开职位"
    if source == "zsb" and any(token in text for token in ("录取", "招生章程")):
        return "本科招生信息"
    return default


def _audience(source: str, text: str) -> str:
    if source == "yjs" or "研究生" in text:
        return "研究生"
    if source == "zsb" or "本科招生" in text:
        return "本科生/考生"
    if source == "jwc" and any(token in text for token in ("学生", "专业目录")):
        return "本科生"
    if source == "xsc":
        return "在校学生"
    if source == "job":
        return "毕业生/求职者"
    if source == "zhku_main":
        return "全校师生/访客"
    return "全校师生"


def _document_type(text: str) -> str:
    rules = (
        (("job_fairs", "event_", "宣讲会", "招聘会"), "招聘活动"),
        (("job_postings",), "职位列表"),
        (("job_",), "职位详情"),
        (("章程",), "招生章程"),
        (("专业目录", "目录"), "专业目录"),
        (("联系方式", "联系"), "联系方式"),
        (("报销", "费用"), "报销指南"),
        (("申请", "申请表", "表"), "申请表"),
        (("指南", "指引", "流程"), "办事指南"),
        (("资料下载", "下载"), "资料下载"),
    )
    for tokens, document_type in rules:
        if any(token in text for token in tokens):
            return document_type
    return "网页资料"


def classify_metadata(
    meta: dict[str, Any], source_dir: str, filename: str = ""
) -> dict[str, Any]:
    """返回带功能分类字段的 metadata 副本，保留已有显式分类。"""
    result = dict(meta)
    source = _source_key(source_dir, filename)
    default_category, default_subcategory = SOURCE_CATEGORIES.get(
        source, (result.get("department") or "其他资料", "其他")
    )
    text = _text(result, filename)
    category = CATEGORY_ALIASES.get(result.get("category", ""), result.get("category")) or default_category
    subcategory = result.get("subcategory") or _subcategory(
        source, text, default_subcategory
    )
    audience = result.get("audience") or _audience(source, text)
    document_type = result.get("document_type") or _document_type(text)
    old_tags = result.get("tags") or []
    if isinstance(old_tags, str):
        old_tags = [tag.strip() for tag in old_tags.split(",")]
    tags = _unique(
        [
            *[str(tag) for tag in old_tags],
            source,
            result.get("department", ""),
            category,
            subcategory,
            audience,
            document_type,
        ]
    )
    for field in ("download_items", "resources", "attachments"):
        raw_items = result.get(field)
        if not raw_items:
            continue
        if isinstance(raw_items, dict):
            raw_items = list(raw_items.values())
        classified_items = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_result = dict(item)
            item_text = " ".join(
                str(item_result.get(key, ""))
                for key in ("name", "title", "filename", "url", "file_url")
            )
            item_subcategory = _subcategory(source, item_text, subcategory)
            item_type = _document_type(item_text)
            item_tags = _unique(
                [
                    *tags,
                    item_subcategory,
                    item_type,
                ]
            )
            item_result.update(
                {
                    "category": category,
                    "subcategory": item_subcategory,
                    "audience": audience,
                    "document_type": item_type,
                    "tags": item_tags,
                }
            )
            classified_items.append(item_result)
        result[field] = classified_items
    result.update(
        {
            "source_key": source,
            "category": category,
            "subcategory": subcategory,
            "audience": audience,
            "document_type": document_type,
            "tags": tags,
        }
    )
    return result


def _metadata_source_key(metadata_dir: Path, path: Path) -> str:
    if path.parent != metadata_dir:
        return path.parent.name
    prefix = path.stem.split("_", 1)[0]
    return prefix if prefix in KNOWN_SOURCE_KEYS else path.stem


def build_functional_index(
    metadata_dir: Path, index_dir: Path
) -> dict[str, Any]:
    """回填 metadata 分类并生成供检索/管理使用的功能索引。"""
    items: list[dict[str, Any]] = []
    for path in sorted(metadata_dir.rglob("*.json")):
        if path.name == "resource_manifest.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        source = _metadata_source_key(metadata_dir, path)
        classified = classify_metadata(data, source, path.name)
        path.write_text(
            json.dumps(classified, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        source_url = classified.get("source_url") or classified.get("url") or ""
        raw_resources = classified.get("download_items") or classified.get("resources") or classified.get("attachments") or []
        if isinstance(raw_resources, dict):
            raw_resources = list(raw_resources.values())
        resources = [
            {
                "name": item.get("name") or item.get("title") or item.get("filename", ""),
                "url": item.get("url") or item.get("file_url", ""),
                "local_path": item.get("local_path", ""),
                "file_type": item.get("file_type", ""),
                "category": item.get("category", classified["category"]),
                "subcategory": item.get("subcategory", classified["subcategory"]),
                "audience": item.get("audience", classified["audience"]),
                "document_type": item.get("document_type", classified["document_type"]),
                "tags": item.get("tags", classified["tags"]),
            }
            for item in raw_resources
            if isinstance(item, dict)
        ]
        items.append(
            {
                "metadata_path": path.relative_to(metadata_dir.parent).as_posix(),
                "title": classified.get("title") or path.stem,
                "source_url": source_url,
                "department": classified.get("department", ""),
                "source_key": classified["source_key"],
                "category": classified["category"],
                "subcategory": classified["subcategory"],
                "audience": classified["audience"],
                "document_type": classified["document_type"],
                "tags": classified["tags"],
                "resources": resources,
            }
        )

    facets: dict[str, dict[str, int]] = {}
    for field in ("category", "subcategory", "audience", "document_type"):
        facets[field] = dict(
            Counter(str(item[field]) for item in items if item.get(field))
        )
    result = {"version": 1, "total": len(items), "facets": facets, "items": items}
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "metadata_by_function.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    result = build_functional_index(
        project_root / "data" / "metadata", project_root / "data" / "indexes"
    )
    print(f"[classification] 已分类 metadata: {result['total']}")


if __name__ == "__main__":
    main()
