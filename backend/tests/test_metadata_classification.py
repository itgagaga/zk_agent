import json
import shutil
import tempfile
from pathlib import Path

import pytest

from crawler.classification import build_functional_index, classify_metadata


@pytest.fixture
def classification_tmp_path():
    root = Path(__file__).resolve().parents[2] / ".tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="classification-test-", dir=root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_classification_adds_function_and_audience_fields():
    result = classify_metadata(
        {
            "title": "研究生招生章程",
            "department": "研究生处",
            "source_url": "https://yjs.example.edu/info/1.htm",
        },
        "yjs",
        "admission_charter.json",
    )

    assert result["category"] == "研究生教育与招生"
    assert result["subcategory"] == "研究生招生"
    assert result["audience"] == "研究生"
    assert result["document_type"] == "招生章程"
    assert "研究生" in result["tags"]


def test_classification_normalizes_legacy_category_alias():
    result = classify_metadata(
        {"title": "机构设置", "category": "学校主站"},
        "zhku_main",
        "jgsz.json",
    )

    assert result["category"] == "学校概况与机构设置"


def test_classification_propagates_to_downloaded_resources():
    result = classify_metadata(
        {
            "title": "学生资料下载",
            "department": "教务部",
            "download_items": [
                {"name": "学生证申请表.docx", "url": "https://example.edu/a.docx"}
            ],
        },
        "jwc",
        "student_downloads.json",
    )

    resource = result["download_items"][0]
    assert resource["category"] == "教学与教务"
    assert resource["subcategory"] == "学生事务"
    assert resource["document_type"] == "申请表"


def test_build_functional_index_writes_classified_metadata(classification_tmp_path):
    tmp_path = classification_tmp_path
    metadata_dir = tmp_path / "metadata"
    metadata_dir.mkdir()
    source_file = metadata_dir / "jwc_xsxz.json"
    source_file.write_text(
        json.dumps(
            {
                "title": "学生下载",
                "department": "教务部",
                "source_url": "https://jwc.example.edu/xsxz.htm",
                "download_items": [
                    {
                        "name": "学生证申请表.docx",
                        "url": "https://jwc.example.edu/form.docx",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = build_functional_index(metadata_dir, tmp_path / "indexes")

    saved = json.loads(source_file.read_text(encoding="utf-8"))
    assert saved["category"] == "教学与教务"
    assert result["total"] == 1
    assert result["items"][0]["subcategory"] == "学生事务"
    assert result["items"][0]["resources"][0]["document_type"] == "申请表"
    assert (tmp_path / "indexes" / "metadata_by_function.json").exists()


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
