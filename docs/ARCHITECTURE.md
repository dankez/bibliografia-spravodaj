# SSS Bibliography: System Architecture

This document describes the design, architecture, and technology stack of the digital bibliography and knowledge portal for **Spravodaj Slovenskej speleologickej spoločnosti (SSS)**.

---

## 🏗️ Design Philosophy

The project is built on the **Hybrid CMS & Static Site** architecture. Instead of developing a custom database, admin panel, and authentication system, we leverage **Zotero** as our content management system (CMS) and database, and **Astro** for our high-performance frontend.

### Key Decisions:
1. **No PDF Duplication:** All PDF documents remain on the original SSS server (`sss.sk`). The website links directly to these files, using physical page offsets (e.g., `#page=28`) to land precisely on the start of each article.
2. **Zotero as a Serverless CMS:** Zotero is a free, open-source reference manager with collaborative libraries. SSS webmasters use the desktop or web Zotero client to edit, organize, and tag articles.
3. **Astro for Static Performance & SEO:** The website is statically generated at build time by pulling data from the Zotero API. This ensures instant loading times, zero server maintenance costs, and perfect indexing by Google Scholar.
4. **Client-side Smart Search:** Search queries are processed instantly in the user's browser using `MiniSearch`, indexing a pre-compiled JSON file.

---

## 📁 Directory Structure

```
sss-bibliografia/
├── data/                  # Raw and parsed bibliographic data (JSON, CSV)
├── docs/                  # System documentation and guides
│   ├── ARCHITECTURE.md    # This file
│   └── PARSING_LOG.md     # Log of the PDF extraction process
├── scripts/               # Python scripts for data migration & AI extraction
│   ├── parse_bibliography.py      # Extracts articles from the historic PDF
│   ├── extract_pdf_fulltext.py    # Builds article-level full-text JSONL from linked PDFs
│   ├── build_research_knowledge_db.py # Builds offline SQLite/FTS research database
│   ├── openai_enrich_knowledge.py # OpenAI/Codex enrichment of extracted full text
│   ├── export_danko_format.py     # Readable Danko bibliography export
│   └── upload_to_zotero.py        # Uploads parsed data to the Zotero API
└── web/                   # Astro web application (frontend)
```

---

## 🔄 Data Ingestion Flow

The bibliographic data covers two periods:

### 1. Historical Data (1970 - 2009)
Parsed from the published book **"Bibliografia Spravodaja SSS"** by Marcel Lalkovič (2011).
- **Extraction:** A Python script uses `pdftotext` to extract the article list and parses it using layout-aware regular expressions.
- **Enrichment:** We map each issue (year, issue number) to the correct PDF URL on `sss.sk`.
- **Upload:** The data is pushed to the Zotero Group Library using the `pyzotero` library.

### 2. Modern & Future Data (2010 - Present)
- **Scraper:** A script scans the `sss.sk/spravodaj/` page for new PDF uploads.
- **AI Extractor:** Newly uploaded PDFs have their table of contents extracted and sent to the default **Codex auth backend** (`codex exec --output-schema`) or optionally to the **OpenAI Responses API** to extract articles, authors, page ranges, attachments, and summaries.
- **Insertion:** Extracted articles are added directly to the Zotero Group Library.

### 3. Full-text Knowledge Layer
For deeper knowledge-base use, PDF issues can be cached locally and split into article-level text records:
- `extract_pdf_fulltext.py` downloads each unique issue PDF once and extracts article page ranges with `pdftotext`.
- `build_research_knowledge_db.py` creates the offline research database without AI calls: it cleans text, trims neighbouring article bleed on shared pages, chunks content for retrieval, builds SQLite FTS5 search, stores citations, JSON-LD, entity links, timelines, and PDF/media references.
- `openai_enrich_knowledge.py` is an optional enrichment pass. It uses Codex auth by default, or OpenAI Structured Outputs when `--ai-backend openai` is selected, to create bibliographic abstracts, Lalkovic-style notes, keywords, entities, cave names, SSS groups, and map/plan flags.
- The research layer is stored outside the default frontend bundle so the public bibliography stays fast, while later editorial tools can retrieve source-linked chunks for long-form AI articles.

---

## 🌐 Tech Stack

- **Data Management:** Zotero API (Group Library)
- **Frontend Framework:** Astro 4.x (Static Site Generation)
- **Styling:** CSS + Tailwind CSS v4
- **Search Engine:** MiniSearch (In-browser search index)
- **GIS Map:** Leaflet.js / OpenStreetMap
- **Research DB:** SQLite FTS5 + JSONL exports
- **AI Processing:** Codex auth backend or OpenAI Responses API with Structured Outputs
- **Hosting:** GitHub Pages or Vercel (Free tier)
