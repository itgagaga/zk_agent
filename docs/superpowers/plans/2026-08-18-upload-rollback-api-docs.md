# Upload Rollback and API Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make user-document replacement failure-safe and synchronize the documented admin API paths with the FastAPI routes.

**Architecture:** Parse and embed the new upload before mutating the current user's records. Keep the old database rows, files, and vectors until the new vector write and database commit succeed; on any later failure, remove only newly created state and restore the old state when necessary. Update the existing development API table to reflect the implemented route paths and explicitly mark the currently stubbed task endpoints.

**Tech Stack:** FastAPI, SQLAlchemy, Chroma wrapper, unittest/pytest, Markdown documentation.

## Global Constraints

- Do not delete or overwrite unrelated user changes in the working tree.
- Preserve the existing “one active private document set per user” replacement behavior.
- Do not change public API response shapes unless required for rollback correctness.
- Tests must exercise real upload orchestration with fakes only at external vector/database boundaries.

---

### Task 1: Make user-document replacement failure-safe

**Files:**
- Modify: `backend/api/upload.py:41-153`
- Test: `backend/tests/test_upload.py`

**Interfaces:**
- Consume the existing `_clear_user_documents`, `get_vector_store`, and `UserDocument` interfaces.
- Produce an upload flow that leaves the previous document intact if vector insertion or database commit fails, and removes newly created vectors/files when the new upload fails after those resources are created.

- [ ] **Step 1: Write the failing regression tests**

  Add tests for two cases: vector insertion failure keeps the old row/file/vector, and database commit failure removes the new vector/file while retaining the old row/file/vector.

- [ ] **Step 2: Run the focused tests and verify they fail for the current destructive ordering**

  Run `python -m pytest backend/tests/test_upload.py -q` and confirm the tests fail because the current implementation clears the old document before the new document is durable.

- [ ] **Step 3: Implement staged replacement and cleanup**

  Change the flow to parse and write the new file/vector first, commit the new row, then remove the old row/file/vector. Track old rows and new resources so exception handling removes only the new state and rolls back the SQLAlchemy session.

- [ ] **Step 4: Run the focused tests and verify they pass**

  Run `python -m pytest backend/tests/test_upload.py -q` and confirm both rollback cases pass.

- [ ] **Step 5: Run the backend regression suite**

  Run `python -m pytest backend/tests -q` and confirm all backend tests pass.

### Task 2: Synchronize documented admin API paths

**Files:**
- Modify: `docs/ZHKU_Campus_Agent_开发.md:589-593`
- Test: `backend/tests/test_api_documentation.py`

**Interfaces:**
- Consume the route declarations in `backend/api/admin.py`.
- Produce documentation that names `/api/admin/kb/rebuild`, `/api/admin/links/check`, and `/api/admin/crawl/run`, while retaining the documented status of unimplemented log/feedback endpoints.

- [ ] **Step 1: Write the failing documentation consistency test**

  Add a test that reads the documentation and asserts the three implemented admin paths are present and the stale `/api/admin/rebuild-kb` and `/api/admin/crawl` paths are absent.

- [ ] **Step 2: Run the focused documentation test and verify it fails**

  Run `python -m pytest backend/tests/test_api_documentation.py -q` and confirm it fails because the document contains the stale paths.

- [ ] **Step 3: Update the documentation table**

  Replace stale paths with the actual FastAPI paths and label the current task endpoints as placeholders until they are implemented.

- [ ] **Step 4: Run the focused documentation test and verify it passes**

  Run `python -m pytest backend/tests/test_api_documentation.py -q` and confirm it passes.

### Task 3: Final verification

**Files:**
- Inspect: `backend/api/upload.py`, `backend/tests/test_upload.py`, `docs/ZHKU_Campus_Agent_开发.md`

- [ ] **Step 1: Run compile and backend tests**

  Run `python -m compileall -q backend crawler analytics` and `python -m pytest backend/tests -q`.

- [ ] **Step 2: Build the frontend**

  Run `npm.cmd run build` from `frontend/`.

- [ ] **Step 3: Review the final diff and working-tree scope**

  Run `git diff --check`, `git diff --stat`, and `git status --short`; confirm only the requested upload, test, plan, and documentation files changed.
