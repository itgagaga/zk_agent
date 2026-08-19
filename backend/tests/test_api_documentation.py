from pathlib import Path


DOC_PATH = Path(__file__).resolve().parents[2] / "docs" / "ZHKU_Campus_Agent_开发.md"


def test_admin_documentation_matches_registered_routes():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "| `POST /api/admin/kb/rebuild` |" in text
    assert "| `GET /api/admin/links/check` |" in text
    assert "| `POST /api/admin/crawl/run` |" in text
    assert "| `POST /api/admin/rebuild-kb` |" not in text
    assert "| `POST /api/admin/crawl` |" not in text
