# Public Resource Acquisition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Download all remaining publicly accessible non-news resources, especially teaching-affairs and graduate downloads, and make the resulting metadata visible to the application.

**Architecture:** Add a shared resource discovery/downloader that handles pagination, detail pages, direct file links, retries, safe filenames, and failure manifests. Update configured crawler entry points to use the shared layer, and update metadata consumers to read the normalized records recursively.

**Tech Stack:** Python, `requests`, BeautifulSoup, pytest, existing `data/raw` and `data/metadata` layout.

**Spec:** `docs/superpowers/specs/2026-08-18-resource-download-design.md`

## Global Constraints

- Do not crawl the news feature.
- Do not batch-download the intentionally abandoned training-plan PDFs.
- Do not bypass CAPTCHA, login, or access controls.
- Do not save an HTML challenge page as a successful document binary.
- Preserve failed resources in a manifest with an explicit status and error.

---

### Task 1: Lock down the shared resource behavior with tests

**Files:**
- Create: `backend/tests/test_resource_download.py`
- Test: `crawler/resource_download.py` (expected new public functions)

**Interfaces:**
- `is_document_link(url: str, label: str = "") -> bool`
- `infer_file_type(url: str, label: str = "") -> str | None`
- `extract_resource_links(html: str, base_url: str) -> list[dict[str, str]]`
- `extract_pagination_links(html: str, base_url: str) -> list[str]`
- `build_metadata_record(...) -> dict[str, Any]`

- [ ] Write tests showing that direct extensions, `download.jsp`, and detail-page links are recognized; navigation links are ignored.
- [ ] Write tests showing file type inference from URL path, query links, and link labels.
- [ ] Write tests showing same-section pagination URLs are discovered and external navigation is ignored.
- [ ] Write tests showing canonical metadata includes `name`, `url`, `source_page_url`, `file_type`, and status fields.
- [ ] Run `python -m pytest backend/tests/test_resource_download.py -q` and verify the tests fail because the module does not exist.

### Task 2: Implement shared discovery and download primitives

**Files:**
- Create: `crawler/resource_download.py`
- Modify: `crawler/common.py` only if the shared layer needs the existing request helper factored without changing callers.
- Test: `backend/tests/test_resource_download.py`

**Interfaces:**
- `discover_resource_pages(start_url: str, *, max_pages: int = 50) -> list[dict[str, Any]]`
- `download_public_resource(resource: dict[str, Any], source_dir: str, *, retries: int = 2) -> dict[str, Any]`
- `write_resource_manifest(source_dir: str, records: list[dict[str, Any]]) -> Path`

- [ ] Implement URL normalization with `urljoin`, same-host checks, and safe filename generation.
- [ ] Implement attachment extraction for file suffixes, `download.jsp`/download endpoints, and detail-page candidates.
- [ ] Implement pagination discovery from next/page/last links while preventing loops and cross-section crawling.
- [ ] Implement bounded retry with `settings.crawl_timeout`, `settings.crawl_user_agent`, and `settings.crawl_delay`.
- [ ] Reject HTML/challenge responses as document downloads and record `status="failed"` plus `error`.
- [ ] Run the focused test file and verify it passes.

### Task 3: Integrate teaching-affairs and graduate download acquisition

**Files:**
- Modify: `crawler/crawl_jwc.py`
- Modify: `crawler/crawl_yjs.py`
- Test: `backend/tests/test_resource_download.py`

- [ ] Update student and graduate list crawlers to traverse all discovered pages.
- [ ] Resolve each detail page to its direct attachment links before downloading.
- [ ] Keep training-plan batch PDFs out of the new download loop.
- [ ] Write canonical `download_items` metadata plus a per-source manifest under `data/metadata/`.
- [ ] Add tests for a paginated list and a detail page containing a `download.jsp` attachment.
- [ ] Run focused tests and verify the existing backend tests still pass.

### Task 4: Integrate attachments from configured auxiliary pages

**Files:**
- Modify: `crawler/crawl_zhku_main.py`
- Modify: `crawler/crawl_extra.py`
- Modify: `crawler/crawl_services.py` only where configured pages expose attachments.
- Test: `backend/tests/test_resource_download.py`

- [ ] Feed configured school, student-affairs, admissions, graduate-extra, and finance pages through shared attachment extraction.
- [ ] Preserve each page's existing cleaned text output while adding canonical resource records.
- [ ] Do not add news traversal or employment scraping.
- [ ] Run focused tests and compile the crawler package.

### Task 5: Make metadata consumers read the generated resources

**Files:**
- Modify: `backend/tools/base.py`
- Modify: `backend/tools/download_tool.py`
- Modify: `backend/tools/major_tool.py` only if canonical records require the same compatibility normalization.
- Test: `backend/tests/test_resource_download.py`

- [ ] Change metadata loading to recursively scan `data/metadata/**/*.json`.
- [ ] Normalize `download_items`, `resources`, and `attachments` into the canonical item shape at read time.
- [ ] Keep existing keyword matching and response shape intact.
- [ ] Test that nested generated metadata is returned by the download tool.
- [ ] Run `python -m pytest backend/tests -q`.

### Task 6: Run discovery, acquisition, and verification

**Files:**
- Generated: `data/raw/**` public resource files
- Generated: `data/metadata/**` manifests and normalized metadata

- [ ] Run a discovery-only pass and record candidate counts by source.
- [ ] Run the actual acquisition pass for the in-scope sources.
- [ ] Report successful downloads, skipped/failed resources, and failure reasons.
- [ ] Run `python -m compileall -q backend crawler analytics` and `python -m pytest backend/tests -q`.
- [ ] Verify the generated manifest has no silent omissions and that the download query can see successful records.
