# Bibliography Backfill Fulltext Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Spravodaj SSS issue metadata after 2009, repair wrong issue years, rebuild the fulltext/research layer, and expose fulltext search without bloating the initial web bundle.

**Architecture:** Keep `articles_with_urls.json` as the canonical public bibliography and use `urls_map.json` as the authoritative issue list for historical backfill. Extract fulltext only after article metadata exists, rebuild `research_knowledge.sqlite`, then export a lazy-loaded browser fulltext index under `web/public/data/`.

**Tech Stack:** Python scripts, pytest, pdftotext/pdfinfo, SQLite FTS5, Astro, MiniSearch.

---

### Task 1: Issue Key Parsing

**Files:**
- Modify: `scripts/ai_scrape_new_issues.py`
- Test: `tests/test_ai_scrape_new_issues.py`

- [ ] Add failing tests for filename-first issue parsing and URL map key parsing.
- [ ] Implement helpers that prefer `urls_map.json` keys, then PDF filename, then visible link text, with upload-folder year only as a final fallback.
- [ ] Verify with `rtk python3 -m pytest tests/test_ai_scrape_new_issues.py -q`.

### Task 2: URL Map Backfill Mode

**Files:**
- Modify: `scripts/ai_scrape_new_issues.py`
- Test: `tests/test_ai_scrape_new_issues.py`

- [ ] Add failing tests for missing issue detection from `urls_map.json`.
- [ ] Add `--from-url-map` and optional issue filters so missing historical issues can be processed without relying on the live page.
- [ ] Verify missing keys include 2010-2024 before running Codex extraction.

### Task 3: Repair Existing Metadata

**Files:**
- Create: `scripts/repair_article_metadata.py`
- Test: `tests/test_repair_article_metadata.py`

- [ ] Add tests for correcting `Spravodaj_2013_kongres.pdf` to `2013/kongres` and `Spravodaj_3_2025_web.pdf` to `2025/3`.
- [ ] Update both canonical and frontend article JSON files.
- [ ] Verify the affected URLs no longer have wrong years.

### Task 4: Fulltext Rebuild

**Files:**
- Existing: `scripts/extract_pdf_fulltext.py`
- Existing: `scripts/build_research_knowledge_db.py`

- [ ] Run full article extraction after backfill.
- [ ] Rebuild `research_knowledge.sqlite` from the complete article list.
- [ ] Verify manifest counts and year coverage.

### Task 5: Lazy Web Fulltext Search

**Files:**
- Create: `scripts/export_web_fulltext_index.py`
- Modify: `web/src/pages/index.astro`

- [ ] Export `web/public/data/fulltext_index.json` from research chunks.
- [ ] Add a fulltext toggle that lazy-loads the JSON and searches chunks with MiniSearch.
- [ ] Verify Astro build and smoke-test that no fulltext JSON is bundled on initial load.
