# New Data Integration Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a trustworthy end-to-end path in which newly crawled downloads and employment records can be precisely filtered, directly browsed, correctly indexed, and safely rebuilt without fabricated metadata.

**Architecture:** Treat normalized metadata as the single source of truth. Downloads use structured filters and server-produced facets; employment keeps aggregate JSON for list APIs and emits one same-stem metadata file per cleaned detail for classification and RAG. Refresh the functional index after crawling and validate employment metadata alignment before any destructive vector-store reset.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, pytest, React 18, Axios, Vite 5, Node.js built-in test runner, JSON metadata, Chroma.

**Spec:** `docs/superpowers/specs/2026-08-18-new-data-integration-remediation-design.md`

## Global Constraints

- Preserve all existing uncommitted user changes. Never use `git reset`, `git checkout --`, or broad staging commands such as `git add .`.
- Several target files are already modified. Inspect `git diff` before editing and use `git add -p <file>` to stage only this plan's hunks.
- Do not add database tables, migrate employment data to MySQL, or add runtime/development dependencies.
- Do not bypass login, CAPTCHA, robots restrictions, or other access controls.
- Keep `job_postings.json` and `job_fairs.json` as the read-only list source; use per-detail metadata only for classification and RAG alignment.
- The canonical employment detail stems are `job_<id>` and `event_<id>`.
- Response metadata comes from the resource/item record first, then its parent metadata, then an empty value. Request parameters must never be echoed as metadata.
- `keyword` is textual matching; `category` and `audience` are exact filters; combined parameters use intersection semantics.
- `total` is the deduplicated count before `top_k` truncation.
- Generated files under `data/` are runtime artifacts and are not staged unless the repository's existing tracking policy explicitly requires them.
- Do not run `python -m crawler.build_kb` without a separate approval at execution time because it deletes and recreates the current vector collections.

## File Structure

| Path | Responsibility |
|---|---|
| `backend/tools/download_tool.py` | Normalize downloadable resources, apply keyword/exact filters, deduplicate, and calculate facets |
| `backend/tools/job_tool.py` | Read and query aggregate employment JSON without exposing file-format details to the API |
| `backend/api/resources.py` | Define typed downloads/jobs HTTP contracts and map tool errors to HTTP responses |
| `crawler/crawl_job.py` | Preserve aggregate lists and emit one metadata file per downloaded employment detail |
| `crawler/classification.py` | Distinguish employment list, job detail, and recruitment-event records |
| `crawler/run_all.py` | Refresh the functional index after all crawl stages |
| `crawler/build_kb.py` | Refresh metadata classification and validate same-stem employment metadata before vector reset |
| `frontend/src/resourceViewModel.js` | Small dependency-free response/query helpers testable with Node's built-in runner |
| `frontend/src/components/EmploymentBrowser.jsx` | Employment list loading, filtering, states, and official-detail cards |
| `frontend/src/pages/DownloadsPage.jsx` | Consume download facets and host the employment tab |
| `frontend/src/styles.css` | Employment browser layout using the existing resource-card visual system |
| `backend/tests/*.py` | Backend regression, contract, crawler, and rebuild-safety tests |
| `frontend/src/resourceViewModel.test.js` | Frontend data-contract tests without adding a test dependency |
| `docs/ZHKU_Campus_Agent_开发.md` | Document the two APIs and safe crawl/index/rebuild sequence |

---

### Task 1: Make download filtering and metadata truthful

**Files:**
- Modify: `backend/tools/download_tool.py:19-58`
- Modify: `backend/tests/test_resource_download.py:45-100`

**Interfaces:**
- Consumes: `BaseTool._load_all_metadata()`, `BaseTool._extract_keywords(question)`, and `BaseTool._keyword_match(text, keywords)`.
- Produces: `await DownloadTool.run(question, category=str | None, audience=str | None, top_k=int) -> {"tool": str, "items": list[dict], "total": int, "facets": {"categories": list[str], "audiences": list[str]}}`.
- Candidate item keys: `title`, `file_url`, `source_page_url`, `publish_date`, `department`, `category`, `subcategory`, `audience`, `document_type`, `file_type`.

- [ ] **Step 1: Add failing tests for exact intersection filters and real item metadata**

Append tests that create two parent metadata files and ensure resource-level fields win:

```python
def test_download_tool_uses_exact_filters_and_resource_metadata(
    monkeypatch, resource_tmp_path
):
    metadata_dir = resource_tmp_path / "metadata" / "mixed"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "resources.json").write_text(
        json.dumps(
            {
                "title": "混合资料",
                "category": "财务与报销",
                "audience": "全校师生",
                "source_url": "https://example.edu/list.htm",
                "download_items": [
                    {
                        "name": "学生证申请表.docx",
                        "url": "https://example.edu/student-card.docx",
                        "source_page_url": "https://example.edu/student-card.htm",
                        "category": "教学与教务",
                        "audience": "本科生",
                    },
                    {
                        "name": "缓考申请表.docx",
                        "url": "https://example.edu/defer.docx",
                        "category": "教学与教务",
                        "audience": "本科生",
                    },
                    {
                        "name": "报销申请表.xlsx",
                        "url": "https://example.edu/expense.xlsx",
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tools_base, "DATA_DIR", resource_tmp_path)

    result = asyncio.run(
        DownloadTool().run(
            "申请表", category="教学与教务", audience="本科生", top_k=1
        )
    )

    assert result["total"] == 2
    assert len(result["items"]) == 1
    assert result["items"][0]["category"] == "教学与教务"
    assert result["items"][0]["audience"] == "本科生"
    assert result["items"][0]["source_page_url"] == (
        "https://example.edu/student-card.htm"
    )
    assert result["facets"]["categories"] == ["教学与教务", "财务与报销"]
```

Add a second assertion-focused test proving exact rather than substring matching:

```python
def test_download_tool_category_is_not_used_as_a_keyword(
    monkeypatch, resource_tmp_path
):
    metadata_dir = resource_tmp_path / "metadata"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "one.json").write_text(
        json.dumps(
            {
                "title": "教学与教务说明",
                "category": "财务与报销",
                "download_items": [
                    {"name": "财务表格.xlsx", "url": "https://example.edu/a.xlsx"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(tools_base, "DATA_DIR", resource_tmp_path)

    result = asyncio.run(DownloadTool().run("", category="教学与教务"))

    assert result["total"] == 0
    assert result["items"] == []
```

- [ ] **Step 2: Run the new tests and verify the current implementation fails**

Run:

```powershell
python -m pytest backend/tests/test_resource_download.py::test_download_tool_uses_exact_filters_and_resource_metadata backend/tests/test_resource_download.py::test_download_tool_category_is_not_used_as_a_keyword -v
```

Expected: FAIL because `DownloadTool.run()` ignores `category`/`audience`, returns parent metadata, lacks facets, and truncates before reporting a reliable filtered total.

- [ ] **Step 3: Implement candidate normalization, filtering, facets, and stable deduplication**

Add a private normalizer and replace the current `run()` body with this sequence:

```python
@staticmethod
def _normalise_item(meta: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    file_url = item.get("url") or item.get("file_url") or ""
    return {
        "title": item.get("name") or item.get("title") or item.get("filename") or "",
        "file_url": file_url,
        "source_page_url": (
            item.get("source_page_url")
            or meta.get("source_page_url")
            or meta.get("source_url")
            or ""
        ),
        "publish_date": item.get("date") or item.get("publish_date") or meta.get("publish_date") or "",
        "department": item.get("department") or meta.get("department") or "",
        "category": item.get("category") or meta.get("category") or "",
        "subcategory": item.get("subcategory") or meta.get("subcategory") or "",
        "audience": item.get("audience") or meta.get("audience") or "",
        "document_type": item.get("document_type") or meta.get("document_type") or "",
        "file_type": item.get("file_type") or "",
    }

async def run(self, question: str, **kwargs: Any) -> dict[str, Any]:
    top_k = int(kwargs.get("top_k", 10))
    category = kwargs.get("category") or None
    audience = kwargs.get("audience") or None
    keywords = self._extract_keywords(question)

    candidates: list[dict[str, Any]] = []
    for meta in self._load_all_metadata():
        for raw_item in meta.get("download_items", []) or []:
            if not isinstance(raw_item, dict):
                continue
            item = self._normalise_item(meta, raw_item)
            if not item["title"]:
                continue
            match_text = f"{item['title']} {self._metadata_search_text(meta)}"
            if keywords and not self._keyword_match(match_text, keywords):
                continue
            candidates.append(item)

    facets = {
        "categories": sorted({item["category"] for item in candidates if item["category"]}),
        "audiences": sorted({item["audience"] for item in candidates if item["audience"]}),
    }
    filtered = [
        item
        for item in candidates
        if (category is None or item["category"] == category)
        and (audience is None or item["audience"] == audience)
    ]

    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in filtered:
        key = (item["title"], item["file_url"] or item["source_page_url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return {
        "tool": self.name,
        "items": unique[:top_k],
        "total": len(unique),
        "facets": facets,
    }
```

Facets are calculated after keyword matching but before category/audience filtering so the selected chip does not disappear from the same response.

- [ ] **Step 4: Run the complete resource-download test file**

Run:

```powershell
python -m pytest backend/tests/test_resource_download.py -q
```

Expected: all tests in the file PASS; the legacy nested-resource tests remain green.

- [ ] **Step 5: Review and commit only Task 1 hunks**

Run:

```powershell
git diff -- backend/tools/download_tool.py backend/tests/test_resource_download.py
git add -p backend/tools/download_tool.py
git add -p backend/tests/test_resource_download.py
git commit -m "fix: apply truthful download metadata filters"
```

Expected: the commit contains only Task 1 changes; unrelated pre-existing hunks remain unstaged.

---

### Task 2: Correct the downloads HTTP contract

**Files:**
- Modify: `backend/api/resources.py:69-85,225-250`
- Create: `backend/tests/test_resources_api.py`

**Interfaces:**
- Consumes: Task 1's `DownloadTool.run()` result.
- Produces: `ListResponse.facets: dict[str, list[str]] | None` and `GET /api/resources/downloads` with true `total`, item metadata, and facets.
- Keeps: `llm_query_optimization` for the academic endpoint.

- [ ] **Step 1: Add a failing direct API contract test**

Create `backend/tests/test_resources_api.py`:

```python
import asyncio

from backend.api import resources


class FakeDownloadTool:
    async def run(self, question, **kwargs):
        assert question == "申请表"
        assert kwargs == {
            "category": "教学与教务",
            "audience": "本科生",
            "top_k": 1,
        }
        return {
            "items": [
                {
                    "title": "学生证申请表.docx",
                    "category": "教学与教务",
                    "audience": "本科生",
                    "file_type": "docx",
                    "source_page_url": "https://example.edu/detail.htm",
                    "file_url": "https://example.edu/form.docx",
                    "publish_date": "2026-08-18",
                    "department": "教务部",
                }
            ],
            "total": 7,
            "facets": {
                "categories": ["教学与教务", "财务与报销"],
                "audiences": ["本科生", "全校师生"],
            },
        }


def test_downloads_api_preserves_tool_metadata_total_and_facets(monkeypatch):
    monkeypatch.setattr(resources, "_download_tool", FakeDownloadTool())

    response = asyncio.run(
        resources.list_downloads(
            keyword="申请表",
            category="教学与教务",
            audience="本科生",
            top_k=1,
        )
    ).model_dump()

    assert response["total"] == 7
    assert response["items"][0]["category"] == "教学与教务"
    assert response["items"][0]["audience"] == "本科生"
    assert response["facets"]["categories"] == ["教学与教务", "财务与报销"]
```

- [ ] **Step 2: Run the test and verify it fails for the existing API behavior**

Run:

```powershell
python -m pytest backend/tests/test_resources_api.py::test_downloads_api_preserves_tool_metadata_total_and_facets -v
```

Expected: FAIL because the API calls the tool with `keyword or category`, omits structured filters/facets, and replaces the true total with `len(items)`.

- [ ] **Step 3: Extend `ListResponse` and map the tool result without fabricating fields**

Add the optional response field:

```python
class ListResponse(BaseModel):
    total: int
    items: list
    facets: dict[str, list[str]] | None = None
    llm_query_optimization: dict | None = Field(
        default=None, description="LLM 关键词优化结果（学术搜索专用）"
    )
```

Replace `list_downloads()` internals with:

```python
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
```

Update the `category` and `audience` query descriptions to say they use exact metadata values returned in `facets`.

- [ ] **Step 4: Run API and resource regressions**

Run:

```powershell
python -m pytest backend/tests/test_resources_api.py backend/tests/test_resource_download.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 5: Review and commit only Task 2 hunks**

Run:

```powershell
git diff -- backend/api/resources.py backend/tests/test_resources_api.py
git add -p backend/api/resources.py
git add backend/tests/test_resources_api.py
git commit -m "fix: expose canonical download facets"
```

---

### Task 3: Emit and classify one metadata file per employment detail

**Files:**
- Modify: `crawler/crawl_job.py:110-215`
- Modify: `crawler/classification.py:53-107`
- Modify: `backend/tests/test_job_crawler.py`
- Modify: `backend/tests/test_metadata_classification.py`

**Interfaces:**
- Produces: `write_detail_metadata(items: list[dict[str, Any]], kind: Literal["job", "event"]) -> int`.
- Produces files: `data/metadata/job/job_<id>.json` and `data/metadata/job/event_<id>.json` for records whose `status == "downloaded"` and whose `id` is non-empty.
- Each detail metadata record contains `id`, `title`, `company`, `source_url`, `publish_date`, `category`, `subcategory`, `audience`, and `document_type`.

- [ ] **Step 1: Add failing crawler tests for same-stem metadata**

Append to `backend/tests/test_job_crawler.py`:

```python
from crawler import crawl_job


def test_write_job_detail_metadata_uses_detail_url(monkeypatch):
    saved = []
    monkeypatch.setattr(
        crawl_job,
        "save_metadata",
        lambda subdir, filename, data: saved.append((subdir, filename, data)),
    )

    count = crawl_job.write_detail_metadata(
        [
            {
                "id": "42",
                "name": "农艺师",
                "company": "广州农业公司",
                "published": "07/18 发布",
                "url": "https://job.example/job-detail?id=42",
                "source_url": "https://job.example/job-list",
                "status": "downloaded",
            },
            {
                "id": "43",
                "name": "失败职位",
                "url": "https://job.example/job-detail?id=43",
                "status": "detail_failed",
            },
        ],
        "job",
    )

    assert count == 1
    assert saved[0][0:2] == ("job", "job_42.json")
    assert saved[0][2]["title"] == "农艺师"
    assert saved[0][2]["source_url"] == "https://job.example/job-detail?id=42"
    assert saved[0][2]["document_type"] == "职位详情"


def test_write_event_detail_metadata_uses_event_stem(monkeypatch):
    saved = []
    monkeypatch.setattr(
        crawl_job,
        "save_metadata",
        lambda subdir, filename, data: saved.append((filename, data)),
    )

    count = crawl_job.write_detail_metadata(
        [
            {
                "id": "7",
                "name": "校园宣讲会",
                "company": "广州农业公司",
                "time": "2026/07/18 14:00 - 16:00",
                "url": "https://job.example/preach-detail?id=7",
                "status": "downloaded",
            }
        ],
        "event",
    )

    assert count == 1
    assert saved[0][0] == "event_7.json"
    assert saved[0][1]["subcategory"] == "校园招聘活动"
    assert saved[0][1]["document_type"] == "招聘活动"
```

- [ ] **Step 2: Add failing classification tests for job and event filenames**

Append to `backend/tests/test_metadata_classification.py`:

```python
@pytest.mark.parametrize(
    ("filename", "subcategory", "document_type"),
    [
        ("job_42.json", "公开职位", "职位详情"),
        ("event_7.json", "校园招聘活动", "招聘活动"),
    ],
)
def test_classification_distinguishes_employment_detail_kinds(
    filename, subcategory, document_type
):
    result = classify_metadata(
        {"title": "就业详情", "source_url": "https://job.example/detail"},
        "job",
        filename,
    )

    assert result["category"] == "就业与招聘"
    assert result["subcategory"] == subcategory
    assert result["audience"] == "毕业生/求职者"
    assert result["document_type"] == document_type
```

- [ ] **Step 3: Run the new tests and verify the missing behavior**

Run:

```powershell
python -m pytest backend/tests/test_job_crawler.py::test_write_job_detail_metadata_uses_detail_url backend/tests/test_job_crawler.py::test_write_event_detail_metadata_uses_event_stem backend/tests/test_metadata_classification.py::test_classification_distinguishes_employment_detail_kinds -v
```

Expected: FAIL because `write_detail_metadata` does not exist and filename-based detail classification is absent.

- [ ] **Step 4: Implement detail classification with specific-rule ordering**

Update the employment branches so aggregate names are checked before generic detail prefixes:

```python
if source == "job":
    if "job_fairs" in text or "event_" in text or any(
        token in text for token in ("宣讲会", "招聘会")
    ):
        return "校园招聘活动"
    if "job_postings" in text or "job_" in text or "职位" in text:
        return "公开职位"
```

In `_document_type`, place these rules before the current generic employment rules:

```python
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
```

Do not classify `job_fairs` as a job detail; rule order is part of the contract.

- [ ] **Step 5: Implement metadata emission and call it after each aggregate crawl**

Import `Literal` and add:

```python
from typing import Any, Literal


def write_detail_metadata(
    items: list[dict[str, Any]], kind: Literal["job", "event"]
) -> int:
    written = 0
    for item in items:
        item_id = str(item.get("id") or "").strip()
        if item.get("status") != "downloaded" or not item_id:
            continue
        is_event = kind == "event"
        save_metadata(
            "job",
            f"{kind}_{item_id}.json",
            {
                "id": item_id,
                "title": item.get("name") or f"就业详情 {item_id}",
                "company": item.get("company") or "",
                "source_url": item.get("url") or "",
                "publish_date": item.get("time") if is_event else item.get("published", ""),
                "category": "就业与招聘",
                "subcategory": "校园招聘活动" if is_event else "公开职位",
                "audience": "毕业生/求职者",
                "document_type": "招聘活动" if is_event else "职位详情",
            },
        )
        written += 1
    return written
```

After the detail-fetch loop in `crawl_job_postings()`, call `write_detail_metadata(jobs, "job")`. After the detail-fetch loop in `crawl_job_fairs()`, call `write_detail_metadata(events, "event")`. Keep the two aggregate `save_metadata` calls unchanged.

- [ ] **Step 6: Run crawler and classification regressions**

Run:

```powershell
python -m pytest backend/tests/test_job_crawler.py backend/tests/test_metadata_classification.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 7: Backfill current local aggregates without network access**

Run this only after the tests pass:

```powershell
python -c "import json; from pathlib import Path; from crawler.crawl_job import write_detail_metadata; p=Path('data/metadata/job'); jobs=json.loads((p/'job_postings.json').read_text(encoding='utf-8'))['items']; events=json.loads((p/'job_fairs.json').read_text(encoding='utf-8'))['items']; print({'jobs': write_detail_metadata(jobs, 'job'), 'events': write_detail_metadata(events, 'event')})"
```

Expected for the 2026-08-18 sample: `{'jobs': 100, 'events': 10}`. Do not stage the generated `data/metadata/job/job_*.json` or `event_*.json` unless repository policy explicitly tracks generated metadata.

- [ ] **Step 8: Review and commit only Task 3 source/test hunks**

Run:

```powershell
git diff -- crawler/crawl_job.py crawler/classification.py backend/tests/test_job_crawler.py backend/tests/test_metadata_classification.py
git add -p crawler/crawl_job.py
git add -p crawler/classification.py
git add -p backend/tests/test_job_crawler.py
git add -p backend/tests/test_metadata_classification.py
git commit -m "feat: align employment details with metadata"
```

---

### Task 4: Add the employment query tool and typed API

**Files:**
- Create: `backend/tools/job_tool.py`
- Create: `backend/tests/test_job_tool.py`
- Modify: `backend/api/resources.py`
- Modify: `backend/tests/test_resources_api.py`

**Interfaces:**
- Produces: `JobDataError(RuntimeError)` for missing, unreadable, or invalid aggregate files.
- Produces: `await JobTool.run(question, kind=Literal["posting", "fair"], company=str | None, top_k=int) -> {"tool": "job_search", "items": list[dict], "total": int}`.
- Produces: `GET /api/resources/jobs?kind=posting|fair&keyword=&company=&top_k=50`.
- Produces: `JobListResponse(total: int, items: list[JobItem])`, keeping employment response validation independent from the generic resource list.
- Normalized job item keys: `id`, `kind`, `title`, `company`, `published`, `time`, `salary`, `education`, `industry`, `location`, `url`.

- [ ] **Step 1: Write failing `JobTool` tests using temporary aggregate files**

Create `backend/tests/test_job_tool.py`:

```python
import asyncio
import json

import pytest

from backend.tools import job_tool
from backend.tools.job_tool import JobDataError, JobTool


def _write_aggregate(root, filename, items):
    path = root / "metadata" / "job"
    path.mkdir(parents=True, exist_ok=True)
    (path / filename).write_text(
        json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8"
    )


def test_job_tool_filters_keyword_company_and_reports_prelimit_total(
    monkeypatch, tmp_path
):
    _write_aggregate(
        tmp_path,
        "job_postings.json",
        [
            {
                "id": "1",
                "name": "Python 开发工程师",
                "company": "甲公司",
                "url": "https://job.example/detail?id=1",
                "status": "downloaded",
            },
            {
                "id": "2",
                "name": "Python 数据工程师",
                "company": "甲公司",
                "url": "https://job.example/detail?id=2",
                "status": "downloaded",
            },
            {
                "id": "3",
                "name": "Java 开发工程师",
                "company": "乙公司",
                "url": "https://job.example/detail?id=3",
                "status": "downloaded",
            },
            {
                "id": "4",
                "name": "失败职位",
                "company": "甲公司",
                "url": "https://job.example/detail?id=4",
                "status": "detail_failed",
            },
        ],
    )
    monkeypatch.setattr(job_tool, "DATA_DIR", tmp_path)

    result = asyncio.run(
        JobTool().run("Python", kind="posting", company="甲公司", top_k=1)
    )

    assert result["total"] == 2
    assert len(result["items"]) == 1
    assert result["items"][0]["kind"] == "posting"
    assert result["items"][0]["title"] == "Python 开发工程师"


def test_job_tool_reports_invalid_json(monkeypatch, tmp_path):
    path = tmp_path / "metadata" / "job"
    path.mkdir(parents=True)
    (path / "job_fairs.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(job_tool, "DATA_DIR", tmp_path)

    with pytest.raises(JobDataError, match="job_fairs.json"):
        asyncio.run(JobTool().run("", kind="fair"))
```

- [ ] **Step 2: Run the tool tests and verify the module is absent**

Run:

```powershell
python -m pytest backend/tests/test_job_tool.py -v
```

Expected: collection/import FAIL because `backend.tools.job_tool` does not exist.

- [ ] **Step 3: Implement `JobTool` with explicit file/error boundaries**

Create `backend/tools/job_tool.py` with these core definitions:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR
from backend.tools.base import BaseTool


class JobDataError(RuntimeError):
    pass


class JobTool(BaseTool):
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
        candidates = []
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

        unique = []
        seen = set()
        for item in candidates:
            if item["url"] in seen:
                continue
            seen.add(item["url"])
            unique.append(item)
        return {"tool": self.name, "items": unique[:top_k], "total": len(unique)}
```

- [ ] **Step 4: Run `JobTool` tests**

Run:

```powershell
python -m pytest backend/tests/test_job_tool.py -q
```

Expected: all tests PASS.

- [ ] **Step 5: Add failing API tests for typed jobs and service errors**

Append to `backend/tests/test_resources_api.py`:

```python
from fastapi import HTTPException

from backend.tools.job_tool import JobDataError


class FakeJobTool:
    async def run(self, question, **kwargs):
        assert question == "Python"
        assert kwargs == {"kind": "posting", "company": "甲公司", "top_k": 1}
        return {
            "total": 2,
            "items": [
                {
                    "id": "1",
                    "kind": "posting",
                    "title": "Python 开发工程师",
                    "company": "甲公司",
                    "published": "2026-08-18",
                    "time": "",
                    "salary": "5K-8K",
                    "education": "本科",
                    "industry": "软件",
                    "location": "广州",
                    "url": "https://job.example/detail?id=1",
                }
            ],
        }


def test_jobs_api_returns_normalized_items(monkeypatch):
    monkeypatch.setattr(resources, "_job_tool", FakeJobTool())
    response = asyncio.run(
        resources.list_jobs(
            kind="posting", keyword="Python", company="甲公司", top_k=1
        )
    ).model_dump()

    assert response["total"] == 2
    assert response["items"][0]["title"] == "Python 开发工程师"
    assert response["items"][0]["url"].endswith("id=1")


def test_jobs_api_maps_data_errors_to_503(monkeypatch):
    class BrokenJobTool:
        async def run(self, question, **kwargs):
            raise JobDataError("损坏的就业数据")

    monkeypatch.setattr(resources, "_job_tool", BrokenJobTool())
    try:
        asyncio.run(
            resources.list_jobs(kind="fair", keyword=None, company=None, top_k=50)
        )
    except HTTPException as error:
        assert error.status_code == 503
        assert error.detail == "就业数据暂不可用"
    else:
        raise AssertionError("expected HTTPException")


def test_jobs_route_rejects_unknown_kind():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(resources.router)
    response = TestClient(app).get("/jobs?kind=unknown")

    assert response.status_code == 422
```

- [ ] **Step 6: Run the API tests and verify the endpoint is absent**

Run:

```powershell
python -m pytest backend/tests/test_resources_api.py::test_jobs_api_returns_normalized_items backend/tests/test_resources_api.py::test_jobs_api_maps_data_errors_to_503 -v
```

Expected: FAIL because `_job_tool`, `JobItem`, `JobListResponse`, and `list_jobs()` do not exist; after the endpoint exists, the route-level test locks in FastAPI's 422 validation.

- [ ] **Step 7: Add typed models, singleton, and the jobs endpoint**

In `backend/api/resources.py`, import `Literal`, `HTTPException`, `JobTool`, and `JobDataError`; instantiate `_job_tool = JobTool()`. Add:

```python
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


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    kind: Literal["posting", "fair"] = Query(default="posting"),
    keyword: str | None = Query(default=None),
    company: str | None = Query(default=None),
    top_k: int = Query(default=50, ge=1, le=100),
) -> JobListResponse:
    try:
        result = await _job_tool.run(
            keyword or "", kind=kind, company=company, top_k=top_k
        )
    except JobDataError as error:
        raise HTTPException(status_code=503, detail="就业数据暂不可用") from error
    return JobListResponse(total=result["total"], items=result["items"])
```

FastAPI's `Literal` validation supplies the required 422 response for any other `kind` value.

- [ ] **Step 8: Run tool/API regressions**

Run:

```powershell
python -m pytest backend/tests/test_job_tool.py backend/tests/test_resources_api.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 9: Review and commit only Task 4 hunks**

Run:

```powershell
git diff -- backend/tools/job_tool.py backend/tests/test_job_tool.py backend/api/resources.py backend/tests/test_resources_api.py
git add backend/tools/job_tool.py backend/tests/test_job_tool.py
git add -p backend/api/resources.py
git add -p backend/tests/test_resources_api.py
git commit -m "feat: expose employment list API"
```

---

### Task 5: Refresh indexes automatically and validate before vector reset

**Files:**
- Modify: `crawler/run_all.py:15-60`
- Modify: `crawler/build_kb.py:19-81,202-226`
- Create: `backend/tests/test_kb_rebuild_safety.py`

**Interfaces:**
- Produces: `refresh_functional_index() -> dict[str, Any]` in `crawler.run_all`.
- Produces: `validate_job_metadata_alignment(cleaned_dir: Path, metadata_dir: Path) -> list[str]` in `crawler.build_kb`.
- Produces: `refresh_metadata_index() -> dict[str, Any]` in `crawler.build_kb`.
- Ordering invariant in `build_kb.main()`: refresh index → validate alignment → reset collections → build campus KB → build document KB.

- [ ] **Step 1: Add failing pure tests for refresh paths and metadata alignment**

Create `backend/tests/test_kb_rebuild_safety.py`:

```python
from pathlib import Path

import pytest

from crawler import build_kb, run_all


def test_validate_job_metadata_alignment_reports_missing_stems(tmp_path):
    cleaned = tmp_path / "cleaned"
    metadata = tmp_path / "metadata"
    cleaned.mkdir()
    metadata.mkdir()
    (cleaned / "job_1.txt").write_text("职位正文", encoding="utf-8")
    (cleaned / "event_2.txt").write_text("活动正文", encoding="utf-8")
    (metadata / "job_1.json").write_text("{}", encoding="utf-8")

    missing = build_kb.validate_job_metadata_alignment(cleaned, metadata)

    assert missing == ["event_2.json"]


def test_build_main_does_not_reset_when_alignment_fails(monkeypatch):
    events = []
    monkeypatch.setattr(build_kb, "refresh_metadata_index", lambda: events.append("refresh"))
    monkeypatch.setattr(
        build_kb,
        "validate_job_metadata_alignment",
        lambda cleaned, metadata: ["job_42.json"],
    )
    monkeypatch.setattr(build_kb, "reset_collections", lambda: events.append("reset"))

    with pytest.raises(RuntimeError, match="job_42.json"):
        build_kb.main()

    assert events == ["refresh"]


def test_run_all_refresh_uses_metadata_and_indexes_paths(monkeypatch, tmp_path):
    metadata = tmp_path / "metadata"
    indexes = tmp_path / "indexes"
    calls = []
    monkeypatch.setattr(run_all, "DATA_METADATA_DIR", metadata)
    monkeypatch.setattr(run_all, "DATA_INDEX_DIR", indexes)
    monkeypatch.setattr(
        run_all,
        "build_functional_index",
        lambda source, target: calls.append((source, target)) or {"total": 9},
    )

    result = run_all.refresh_functional_index()

    assert result == {"total": 9}
    assert calls == [(metadata, indexes)]
```

- [ ] **Step 2: Run the safety tests and verify the helpers are absent**

Run:

```powershell
python -m pytest backend/tests/test_kb_rebuild_safety.py -v
```

Expected: FAIL because the three new helper functions and ordering guard do not exist.

- [ ] **Step 3: Add reusable index refresh helpers**

In `crawler/run_all.py`, import `Any`, `DATA_DIR`, `DATA_METADATA_DIR`, and `build_functional_index`, define `DATA_INDEX_DIR = DATA_DIR / "indexes"`, then add:

```python
def refresh_functional_index() -> dict[str, Any]:
    result = build_functional_index(DATA_METADATA_DIR, DATA_INDEX_DIR)
    print(f"[run_all] 功能索引已更新: {result['total']} 条 metadata")
    return result
```

Call `refresh_functional_index()` after the final crawl stage and before the completion banner. The existing stage-level exception handling means this still runs after any earlier non-fatal crawl failure.

In `crawler/build_kb.py`, add:

```python
from crawler.classification import build_functional_index, classify_metadata


def refresh_metadata_index() -> dict[str, Any]:
    return build_functional_index(DATA_METADATA_DIR, DATA_METADATA_DIR.parent / "indexes")


def validate_job_metadata_alignment(
    cleaned_dir: Path, metadata_dir: Path
) -> list[str]:
    if not cleaned_dir.exists():
        return []
    missing = []
    for pattern in ("job_*.txt", "event_*.txt"):
        for text_file in sorted(cleaned_dir.glob(pattern)):
            expected = metadata_dir / f"{text_file.stem}.json"
            if not expected.exists():
                missing.append(expected.name)
    return sorted(missing)
```

- [ ] **Step 4: Enforce safe ordering before `reset_collections()`**

Change `build_kb.main()` to:

```python
def main() -> None:
    print("[build_kb] 刷新 metadata 功能索引 ...")
    refresh_metadata_index()
    missing = validate_job_metadata_alignment(
        DATA_CLEANED_DIR / "job", DATA_METADATA_DIR / "job"
    )
    if missing:
        preview = ", ".join(missing[:10])
        raise RuntimeError(f"就业正文缺少同名 metadata: {preview}")

    print("[build_kb] 开始构建向量知识库 ...")
    print("[build_kb] 清空旧集合 ...")
    reset_collections()
    campus_count = build_campus_kb()
    print(f"[build_kb] 官网知识库写入 chunks: {campus_count}")
    doc_count = build_document_kb()
    print(f"[build_kb] 智能文档知识库写入 chunks: {doc_count}")
    print("[build_kb] 完成")
```

This check must remain before the first call that can delete vector data.

- [ ] **Step 5: Run safety and classification tests**

Run:

```powershell
python -m pytest backend/tests/test_kb_rebuild_safety.py backend/tests/test_metadata_classification.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 6: Regenerate the non-vector functional index and inspect employment counts**

Run:

```powershell
python -m crawler.classification
python -c "import json; from pathlib import Path; p=Path('data/indexes/metadata_by_function.json'); d=json.loads(p.read_text(encoding='utf-8')); jobs=[x for x in d['items'] if x.get('source_key')=='job']; print({'total': d['total'], 'job_items': len(jobs), 'empty_titles': sum(not x.get('title') for x in jobs), 'empty_urls': sum(not x.get('source_url') for x in jobs)})"
```

Expected after Task 3 backfill: at least 113 job-source index entries (100 jobs, 10 events, 2 aggregates, and the existing employment-service metadata), with zero empty titles/URLs among the 110 detail entries.

- [ ] **Step 7: Review and commit only Task 5 source/test hunks**

Run:

```powershell
git diff -- crawler/run_all.py crawler/build_kb.py backend/tests/test_kb_rebuild_safety.py
git add -p crawler/run_all.py
git add -p crawler/build_kb.py
git add backend/tests/test_kb_rebuild_safety.py
git commit -m "fix: validate metadata before knowledge-base reset"
```

---

### Task 6: Replace stale download categories and add the employment browser

**Files:**
- Create: `frontend/src/resourceViewModel.js`
- Create: `frontend/src/resourceViewModel.test.js`
- Create: `frontend/src/components/EmploymentBrowser.jsx`
- Modify: `frontend/src/pages/DownloadsPage.jsx:1-20,60,165-205,304-400`
- Modify: `frontend/src/styles.css:4907-5214,5467-5524`
- Modify: `frontend/package.json`

**Interfaces:**
- Consumes: Task 2 downloads response facets and Task 4 jobs API.
- Produces: `downloadCategories(response) -> string[]` and `jobQuery(kind, keyword, company, topK) -> object`.
- Produces: `<EmploymentBrowser />` with `posting`/`fair` sub-tabs, keyword/company filters, explicit loading/error/empty states, and official-detail links.

- [ ] **Step 1: Add dependency-free failing view-model tests**

Create `frontend/src/resourceViewModel.test.js`:

```javascript
import test from 'node:test'
import assert from 'node:assert/strict'
import { downloadCategories, jobQuery } from './resourceViewModel.js'

test('download categories come only from response facets', () => {
  assert.deepEqual(
    downloadCategories({ facets: { categories: ['教学与教务', '就业与招聘'] } }),
    ['教学与教务', '就业与招聘'],
  )
  assert.deepEqual(downloadCategories({}), [])
})

test('job query keeps the typed kind and omits empty filters', () => {
  assert.deepEqual(jobQuery('posting', 'Python', '', 50), {
    kind: 'posting',
    keyword: 'Python',
    top_k: 50,
  })
})
```

Add a script without adding dependencies:

```json
"test": "node --test src/resourceViewModel.test.js"
```

- [ ] **Step 2: Run the frontend test and verify the helper is absent**

Run:

```powershell
npm test
```

Working directory: `frontend/`.

Expected: FAIL because `resourceViewModel.js` does not exist.

- [ ] **Step 3: Implement the view-model helpers**

Create `frontend/src/resourceViewModel.js`:

```javascript
export function downloadCategories(response) {
  const values = response?.facets?.categories
  return Array.isArray(values) ? values.filter(Boolean) : []
}

export function jobQuery(kind, keyword, company, topK = 50) {
  const params = { kind, top_k: topK }
  if (keyword.trim()) params.keyword = keyword.trim()
  if (company.trim()) params.company = company.trim()
  return params
}
```

- [ ] **Step 4: Run the view-model test**

Run:

```powershell
npm test
```

Working directory: `frontend/`.

Expected: 2 tests PASS.

- [ ] **Step 5: Replace the hard-coded download categories with API facets**

In `DownloadsPage.jsx`:

1. Delete `DOWNLOAD_CATEGORIES`.
2. Import `downloadCategories`.
3. Add `const [downloadCategoriesState, setDownloadCategoriesState] = useState([])` beside the other download state.
4. In `loadDownloads()`, after receiving `resp`, set both items and facets:

```javascript
const data = resp.data || {}
setDownloadItems(data.items || [])
setDownloadTotal(data.total || 0)
setDownloadCategoriesState(downloadCategories(data))
```

5. Render `downloadCategoriesState.map(...)` in place of `DOWNLOAD_CATEGORIES.map(...)`.
6. Keep only the “全部” chip when facets are empty; do not restore the legacy list.

- [ ] **Step 6: Implement the self-contained employment browser**

Create `frontend/src/components/EmploymentBrowser.jsx`. Use `axios`, `ExternalLink`, `Search`, and `BriefcaseBusiness`; keep the API call and state inside the component:

```jsx
import { useEffect, useState } from 'react'
import axios from 'axios'
import { BriefcaseBusiness, ExternalLink, Search } from 'lucide-react'
import { jobQuery } from '../resourceViewModel'

export default function EmploymentBrowser() {
  const [kind, setKind] = useState('posting')
  const [keyword, setKeyword] = useState('')
  const [company, setCompany] = useState('')
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    load('posting')
  }, [])

  async function load(nextKind = kind) {
    setLoading(true)
    setError('')
    try {
      const response = await axios.get('/api/resources/jobs', {
        params: jobQuery(nextKind, keyword, company, 50),
      })
      setItems(response.data?.items || [])
      setTotal(response.data?.total || 0)
    } catch {
      setItems([])
      setTotal(0)
      setError('就业数据暂时无法读取，请稍后再试。')
    } finally {
      setLoading(false)
    }
  }

  function selectKind(nextKind) {
    setKind(nextKind)
    load(nextKind)
  }

  return (
    <div className="employment-browser">
      <div className="agent-search-heading">
        <div><div className="eyebrow">CAREER</div><h2>就业信息</h2></div>
        <span>{loading ? '正在检索…' : `已找到 ${total} 条信息`}</span>
      </div>
      <div className="agent-filter-chips">
        <button className={kind === 'posting' ? 'active' : ''} onClick={() => selectKind('posting')}>公开职位</button>
        <button className={kind === 'fair' ? 'active' : ''} onClick={() => selectKind('fair')}>招聘活动</button>
      </div>
      <div className="employment-search-row">
        <label><Search size={17} /><input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="职位、活动或行业" /></label>
        <input value={company} onChange={(event) => setCompany(event.target.value)} placeholder="公司名称" />
        <button className="btn-primary" onClick={() => load()} disabled={loading}>搜索</button>
      </div>
      {error ? (
        <div className="agent-empty-state"><h3>{error}</h3></div>
      ) : items.length === 0 ? (
        <div className="agent-empty-state"><BriefcaseBusiness size={34} /><h3>当前条件下暂无就业信息</h3></div>
      ) : (
        <div className="resource-result-grid">
          {items.map((item) => (
            <article className="resource-result-card" key={`${item.kind}-${item.id}`}>
              <div className="resource-result-body">
                <h3>{item.title}</h3>
                <div className="resource-result-meta">
                  {item.company && <span>{item.company}</span>}
                  {(item.published || item.time) && <span>{item.published || item.time}</span>}
                  {item.location && <span>{item.location}</span>}
                  {item.salary && <span>{item.salary}</span>}
                  {item.education && <span>{item.education}</span>}
                </div>
                <div className="resource-result-actions">
                  <a href={item.url} target="_blank" rel="noreferrer">查看官方详情 <ExternalLink size={14} /></a>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  )
}
```

The error branch must be evaluated before the empty branch so transport failures are not presented as zero results.

- [ ] **Step 7: Add the third top-level tab and render the component**

Import `EmploymentBrowser` and add a button with `activeTab === 'employment'`. Replace the two-way conditional with explicit three-way rendering:

```jsx
// `DownloadsPage.jsx:324` remains the opening of the conditional:
{activeTab === 'downloads' ? (

// Change the separator before the existing services fragment from `) : (` to:
) : activeTab === 'services' ? (

// Change the final close of that conditional from `)}` to:
) : (
  <EmploymentBrowser />
)}
```

The downloads and services bodies remain inline. In this step, modify only the two conditional separators shown above; the facets-loop change is already isolated in Step 5. Do not extract or otherwise edit the JSX inside either branch.

- [ ] **Step 8: Add focused responsive styles**

Add styles using existing variables and card classes:

```css
.employment-browser {
  display: grid;
  gap: 20px;
}

.employment-search-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(180px, 0.45fr) auto;
  gap: 12px;
  align-items: center;
}

.employment-search-row label {
  display: flex;
  align-items: center;
  gap: 8px;
}

.employment-search-row input {
  width: 100%;
  min-height: 44px;
  padding: 0 14px;
  border: 1.5px solid var(--color-dust-taupe);
  border-radius: var(--radius-pill);
  background: var(--color-canvas);
}

@media (max-width: 720px) {
  .employment-search-row {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 9: Run frontend tests and production build**

Run:

```powershell
npm test
npm run build
```

Working directory: `frontend/`.

Expected: 2 Node tests PASS and Vite exits 0 with a production bundle.

- [ ] **Step 10: Review and commit only Task 6 hunks**

Run:

```powershell
git diff -- frontend/package.json frontend/src/resourceViewModel.js frontend/src/resourceViewModel.test.js frontend/src/components/EmploymentBrowser.jsx frontend/src/pages/DownloadsPage.jsx frontend/src/styles.css
git add frontend/package.json frontend/src/resourceViewModel.js frontend/src/resourceViewModel.test.js frontend/src/components/EmploymentBrowser.jsx
git add -p frontend/src/pages/DownloadsPage.jsx
git add -p frontend/src/styles.css
git commit -m "feat: browse employment data in resource hub"
```

---

### Task 7: Document and verify the complete data path

**Files:**
- Modify: `docs/ZHKU_Campus_Agent_开发.md`
- Verify: all files from Tasks 1-6

**Interfaces:**
- Consumes: all completed task contracts.
- Produces: documented API examples, maintenance commands, measured local-data results, and a final verification record.

- [ ] **Step 1: Update API documentation with exact contracts**

Add rows for:

```markdown
| `GET /api/resources/downloads` | 资料关键词检索、metadata 精确分类/受众过滤，并返回可用 facets |
| `GET /api/resources/jobs` | 按 `kind=posting|fair`、关键词和公司查询公开就业信息 |
```

Document these examples:

```text
GET /api/resources/downloads?keyword=申请表&category=教学与教务&audience=本科生&top_k=20
GET /api/resources/jobs?kind=posting&keyword=Python&company=广州&top_k=50
GET /api/resources/jobs?kind=fair&keyword=宣讲会&top_k=50
```

Document the safe maintenance order:

```powershell
python -m crawler.run_all
python -m crawler.classification
# crawler.build_kb deletes/recreates vector collections; run only after alignment checks and explicit approval
python -m crawler.build_kb
```

- [ ] **Step 2: Run the complete relevant backend test suite**

Run:

```powershell
python -m pytest backend/tests/test_resource_download.py backend/tests/test_resources_api.py backend/tests/test_job_crawler.py backend/tests/test_job_tool.py backend/tests/test_metadata_classification.py backend/tests/test_kb_rebuild_safety.py -q
```

Expected: every selected test PASS with zero failures. A pytest cache warning caused by the local workspace permission profile may be reported but does not change the test exit code.

- [ ] **Step 3: Run the frontend test and build from a clean process**

Run:

```powershell
npm test
npm run build
```

Working directory: `frontend/`.

Expected: Node tests PASS and Vite exits 0.

- [ ] **Step 4: Verify current aggregate API counts through the tool**

Run this read-only command:

```powershell
python -c "import asyncio; from backend.tools.job_tool import JobTool; print({'posting': asyncio.run(JobTool().run('', kind='posting', top_k=100))['total'], 'fair': asyncio.run(JobTool().run('', kind='fair', top_k=100))['total']})"
```

Expected for the 2026-08-18 sample: `posting=100`, `fair=10`.

- [ ] **Step 5: Verify same-stem employment metadata and functional-index quality**

Run:

```powershell
python -c "import json; from pathlib import Path; c=Path('data/cleaned/job'); m=Path('data/metadata/job'); texts=list(c.glob('job_*.txt'))+list(c.glob('event_*.txt')); missing=[f'{p.stem}.json' for p in texts if not (m/f'{p.stem}.json').exists()]; print({'texts': len(texts), 'missing': missing[:10], 'missing_count': len(missing)})"
python -m crawler.classification
```

Expected: `missing_count=0`; functional index generation exits 0.

- [ ] **Step 6: Obtain approval before destructive vector rebuild**

Present the successful alignment/test evidence and ask explicitly whether to run:

```powershell
python -m crawler.build_kb
```

Do not run it in the same step as the approval request. If approved, run it once and verify the log shows metadata refresh before collection deletion, followed by non-zero campus chunk count.

- [ ] **Step 7: Inspect final diffs and generated artifacts**

Run:

```powershell
git status --short
git diff --check
git diff --stat
```

Expected: no whitespace errors. Confirm generated `data/` files are not accidentally staged and pre-existing user modifications remain intact.

- [ ] **Step 8: Stage documentation hunk and commit the final documentation update**

Run:

```powershell
git add -p docs/ZHKU_Campus_Agent_开发.md
git commit -m "docs: explain resource and employment data flow"
```

Do not stage unrelated existing edits in the same documentation file.

## Completion Checklist

- [ ] Download category and audience filters are exact and use intersection semantics.
- [ ] Download responses preserve item/parent metadata priority and report pre-limit totals.
- [ ] Download category chips come only from real API facets.
- [ ] Employment aggregate JSON remains the list API source.
- [ ] Every downloaded `job_*.txt` and `event_*.txt` has same-stem metadata with the official detail URL.
- [ ] `/api/resources/jobs` validates `kind`, filters lists, and maps unreadable data to 503.
- [ ] `run_all` refreshes the functional index after crawl stages.
- [ ] `build_kb` validates metadata before deleting vector collections.
- [ ] Employment UI distinguishes loading, transport error, and empty results.
- [ ] Backend tests, frontend Node tests, and Vite production build pass.
- [ ] No database/dependency migration and no access-control bypass were introduced.
- [ ] Existing uncommitted user work and generated-data staging policy were preserved.
