import shutil
import tempfile
from pathlib import Path

import pytest

from crawler import build_kb, run_all


@pytest.fixture
def safety_tmp_path():
    root = Path(__file__).resolve().parents[2] / ".tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="kb-safety-test-", dir=root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_validate_job_metadata_alignment_reports_missing_stems(safety_tmp_path):
    cleaned = safety_tmp_path / "cleaned"
    metadata = safety_tmp_path / "metadata"
    cleaned.mkdir()
    metadata.mkdir()
    (cleaned / "job_1.txt").write_text("职位正文", encoding="utf-8")
    (cleaned / "event_2.txt").write_text("活动正文", encoding="utf-8")
    (metadata / "job_1.json").write_text("{}", encoding="utf-8")

    missing = build_kb.validate_job_metadata_alignment(cleaned, metadata)

    assert missing == ["event_2.json"]


def test_validate_kb_inputs_checks_nested_metadata_locations(safety_tmp_path):
    cleaned = safety_tmp_path / "cleaned"
    metadata = safety_tmp_path / "metadata"
    (cleaned / "zsb").mkdir(parents=True)
    (metadata / "zsb").mkdir(parents=True)
    (cleaned / "zsb" / "charter.txt").write_text("正文", encoding="utf-8")
    (cleaned / "zsb" / "missing.txt").write_text("正文", encoding="utf-8")
    (metadata / "zsb" / "charter.json").write_text("{}", encoding="utf-8")

    assert build_kb.validate_kb_inputs(cleaned, metadata) == ["zsb/missing.json"]


def test_chunk_profiles_are_explicitly_separate():
    campus = build_kb.chunk_profile("campus")
    document = build_kb.chunk_profile("document")

    assert set(campus) == {"chunk_size", "chunk_overlap", "parent_max_size"}
    assert set(document) == set(campus)


def test_build_main_does_not_reset_when_alignment_fails(monkeypatch):
    events = []
    monkeypatch.setattr(
        build_kb, "refresh_metadata_index", lambda: events.append("refresh")
    )
    monkeypatch.setattr(
        build_kb,
        "validate_job_metadata_alignment",
        lambda cleaned, metadata: ["job_42.json"],
    )
    monkeypatch.setattr(build_kb, "reset_collections", lambda: events.append("reset"))

    with pytest.raises(RuntimeError, match="job_42.json"):
        build_kb.main()

    assert events == ["refresh"]


def test_run_all_refresh_uses_metadata_and_indexes_paths(monkeypatch, safety_tmp_path):
    metadata = safety_tmp_path / "metadata"
    indexes = safety_tmp_path / "indexes"
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
