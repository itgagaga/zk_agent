import asyncio
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from backend.tools import job_tool
from backend.tools.job_tool import JobDataError, JobTool


@pytest.fixture
def job_tmp_path():
    root = Path(__file__).resolve().parents[2] / ".tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="job-tool-test-", dir=root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _write_aggregate(root, filename, items):
    path = root / "metadata" / "job"
    path.mkdir(parents=True, exist_ok=True)
    (path / filename).write_text(
        json.dumps({"items": items}, ensure_ascii=False), encoding="utf-8"
    )


def test_job_tool_filters_keyword_company_and_reports_prelimit_total(
    monkeypatch, job_tmp_path
):
    _write_aggregate(
        job_tmp_path,
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
    monkeypatch.setattr(job_tool, "DATA_DIR", job_tmp_path)

    result = asyncio.run(
        JobTool().run("Python", kind="posting", company="甲公司", top_k=1)
    )

    assert result["total"] == 2
    assert len(result["items"]) == 1
    assert result["items"][0]["kind"] == "posting"
    assert result["items"][0]["title"] == "Python 开发工程师"


def test_job_tool_reports_invalid_json(monkeypatch, job_tmp_path):
    path = job_tmp_path / "metadata" / "job"
    path.mkdir(parents=True)
    (path / "job_fairs.json").write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(job_tool, "DATA_DIR", job_tmp_path)

    with pytest.raises(JobDataError, match="job_fairs.json"):
        asyncio.run(JobTool().run("", kind="fair"))
