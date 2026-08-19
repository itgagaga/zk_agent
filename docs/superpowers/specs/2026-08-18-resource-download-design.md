# Public Resource Acquisition Design

## Goal

Complete acquisition of publicly accessible non-news resources that are still in scope, especially the teaching-affairs and graduate download sections, without attempting to bypass CAPTCHA, login, or access controls.

## Scope

- In scope: public HTML pages and downloadable PDF/DOC/DOCX/XLS/XLSX/ZIP/RAR resources linked from configured school, teaching-affairs, graduate, student-affairs, admissions, and finance pages.
- Explicitly out of scope: the news crawler and the intentionally abandoned training-plan PDF batch.
- Conditional: the employment crawler remains a known unimplemented area unless separately approved.

## Design

Use one shared resource-discovery and download layer. It will normalize direct file links, `download.jsp` links, and detail-page links; follow same-section pagination; resolve attachments from detail pages; download public files into `data/raw/<source>/`; and emit one normalized metadata record per resource.

The normalized record uses `download_items`-compatible fields: `name`, `url`, `source_page_url`, `file_type`, `local_path`, `status`, and `error`. Existing `resources` and `attachments` fields remain readable for compatibility, but newly generated download records use the canonical shape.

Metadata consumers will recursively load JSON files and accept the canonical download fields. Failed downloads will remain in the manifest with an error status so missing material is visible and rerunnable.

## Safety and Reliability

- Only HTTP(S) public URLs discovered from configured pages are fetched.
- Requests use the configured user agent, timeout, bounded retries, and delay.
- HTML responses are never saved as successful document binaries.
- CAPTCHA, login, non-document responses, and HTTP failures are recorded as failures.
- No browser automation is required for ordinary public links; browser interaction is a fallback only when a public page cannot be inspected with normal HTTP.

## Verification

- Unit tests cover URL classification, extension inference, pagination discovery, detail-page attachment extraction, and recursive metadata loading.
- A read-only discovery pass reports counts before download.
- A real acquisition pass writes the resource files and manifest, followed by a summary of success/failure counts.
