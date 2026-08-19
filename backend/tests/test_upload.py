import asyncio
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import backend.api.upload as upload_api


class FakeUpload:
    filename = "new.txt"

    async def read(self):
        return b"new document"


class FakeQuery:
    def __init__(self, db):
        self.db = db

    def filter(self, *args):
        return self

    def all(self):
        return list(self.db.rows)


class FakeDB:
    def __init__(self, rows, *, fail_commit=False):
        self.rows = list(rows)
        self._transaction_rows = list(self.rows)
        self.fail_commit = fail_commit
        self.deleted = []
        self.rolled_back = False

    def query(self, model):
        return FakeQuery(self)

    def add(self, row):
        self.rows.append(row)

    def delete(self, row):
        self.deleted.append(row)
        if row in self.rows:
            self.rows.remove(row)

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("database unavailable")
        self._transaction_rows = list(self.rows)

    def rollback(self):
        self.rows = list(self._transaction_rows)
        self.rolled_back = True


class FakeStore:
    def __init__(self, *, fail_add=False):
        self.fail_add = fail_add
        self.attempted_doc_ids = []
        self.added_doc_ids = []
        self.deleted_doc_ids = []

    def add_documents(self, *, ids, texts, metadatas, collection):
        self.attempted_doc_ids.append(metadatas[0]["doc_id"])
        if self.fail_add:
            raise RuntimeError("embedding unavailable")
        self.added_doc_ids.append(metadatas[0]["doc_id"])

    def delete_documents(self, *, ids=None, where=None, collection):
        if where and "doc_id" in where:
            self.deleted_doc_ids.append(where["doc_id"])


def _configure_upload_test(monkeypatch, tmp_path, store, db):
    old_path = tmp_path / "old.txt"
    old_path.write_text("old document", encoding="utf-8")
    old_row = SimpleNamespace(
        user_id=7,
        doc_id="old-doc",
        file_path="old.txt",
    )
    db.rows[:] = [old_row]
    db._transaction_rows = list(db.rows)

    monkeypatch.setattr(
        upload_api,
        "parse_file",
        lambda path: {"full_text": "new document"},
        raising=False,
    )
    monkeypatch.setattr(upload_api, "split_document", lambda *args, **kwargs: [SimpleNamespace()])
    monkeypatch.setattr(
        upload_api,
        "records_to_store_payload",
        lambda records, doc_id, metadata: (
            [f"{doc_id}_0"],
            ["new document"],
            [metadata],
        ),
    )
    monkeypatch.setattr(upload_api, "get_vector_store", lambda: store)
    monkeypatch.setattr(upload_api, "user_uploads_dir", lambda user_id: tmp_path)
    monkeypatch.setattr(upload_api, "resolve_user_file", lambda value: tmp_path / Path(value).name)
    monkeypatch.setattr(upload_api, "to_data_relative", lambda value: Path(value).name)
    return old_row, old_path


@pytest.fixture
def upload_tmp_path():
    root = Path(__file__).resolve().parents[2] / ".tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="upload-test-", dir=root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_vector_write_failure_keeps_previous_document(monkeypatch, upload_tmp_path):
    store = FakeStore(fail_add=True)
    db = FakeDB([])
    old_row, old_path = _configure_upload_test(monkeypatch, upload_tmp_path, store, db)

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        asyncio.run(
            upload_api.upload_file(
                file=FakeUpload(),
                department="docs",
                current_user=SimpleNamespace(id=7),
                db=db,
            )
        )

    assert db.rows == [old_row]
    assert old_path.exists()
    assert store.deleted_doc_ids == [store.attempted_doc_ids[0]]
    assert store.deleted_doc_ids[0] != old_row.doc_id


def test_database_commit_failure_cleans_new_state_and_keeps_previous_document(
    monkeypatch, upload_tmp_path
):
    store = FakeStore()
    db = FakeDB([], fail_commit=True)
    old_row, old_path = _configure_upload_test(monkeypatch, upload_tmp_path, store, db)

    with pytest.raises(RuntimeError, match="database unavailable"):
        asyncio.run(
            upload_api.upload_file(
                file=FakeUpload(),
                department="docs",
                current_user=SimpleNamespace(id=7),
                db=db,
            )
        )

    assert db.rows == [old_row]
    assert db.rolled_back
    assert old_path.exists()
    assert store.deleted_doc_ids == [store.added_doc_ids[0]]

    uploaded_files = [path for path in upload_tmp_path.iterdir() if path.name != "old.txt"]
    assert uploaded_files == []


def test_successful_upload_replaces_previous_document_after_commit(
    monkeypatch, upload_tmp_path
):
    store = FakeStore()
    db = FakeDB([])
    old_row, old_path = _configure_upload_test(monkeypatch, upload_tmp_path, store, db)

    asyncio.run(
        upload_api.upload_file(
            file=FakeUpload(),
            department="docs",
            current_user=SimpleNamespace(id=7),
            db=db,
        )
    )

    assert old_row not in db.rows
    assert len(db.rows) == 1
    assert db.rows[0].doc_id == store.added_doc_ids[0]
    assert not old_path.exists()
    assert (upload_tmp_path / f"{store.added_doc_ids[0]}.txt").exists()
    assert store.deleted_doc_ids == [old_row.doc_id]
