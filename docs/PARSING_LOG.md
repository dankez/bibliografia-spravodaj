# Parsing Log: Historic Bibliography (1970 - 2009)

This log details the execution, methodology, and validation of the parsing process for the historic bibliography of **Spravodaj SSS**.

---

## 📅 Execution Details

- **Date:** 2026-06-15
- **Source File:** `Spravodaj-bibliografia.pdf` (Marcel Lalkovič, 2011)
- **Tool used for text extraction:** `pdftotext` (system binary)
- **Parser script:** [parse_bibliography.py](file:///home/dankez/Downloads/sss-bibliografia/scripts/parse_bibliography.py)
- **Output JSON file:** [articles.json](file:///home/dankez/Downloads/sss-bibliografia/data/articles.json)

---

## 🛠️ Parsing Methodology

The extraction of 40 years of bibliographic metadata (representing 2,535 articles) was carried out as follows:

### 1. Raw Text Extraction
Using `pdftotext`, we extracted layout-preserved text from page 9 to 158 of the PDF file:
```bash
pdftotext -f 9 -l 158 Spravodaj-bibliografia.pdf sss-bibliografia/data/raw_text.txt
```
Page breaks and system artifacts (form-feed characters `\x0c`, headers/footers like `"Bibliografia Spravodaja SSS"`, page numbers, and publication year markers) were cleaned up programmatically.

### 2. State-Machine Based Parser
A custom Python script parsed the cleaned text line-by-line using a state-machine model:
- **Year/Issue Tracking:** Detected year headings (e.g., `Ročník 1970 (I.)`) and issue numbers (e.g., `Číslo 2`) to maintain the active context for subsequent entries.
- **Multi-line Headers:** Handled long article titles that span multiple lines. The parser continues accumulating header lines until it detects the page range suffix (e.g., `, s. 26 – 29`).
- **Robust Author/Title Parsing:**
  - Standard format: `Author: Title` separated by a colon.
  - Special handles for typo entries where colons were omitted or written as dots (e.g. `Roda, Š. Title` or `/La/ Title`).
  - Automatically resolved and split multiple authors (separated by commas).
  - Extracted optional content indicators (`4 obr.`, `1 pl. j.`, `res.`, `lit.`) and stored them as structured tags in the `extras` field.
  - Handled entries without authors (defaulting to `"Anonymus"`).

### 3. Sequential Constraint (False Positive Elimination)
Initially, lists inside article abstracts (e.g. `1. stretnutie speleológov...` or `5. VZ SSS...`) triggered false positives, thinking they were new article headers.
We resolved this by enforcing a **strict sequential numbering constraint**:
- An article is only started if its ID matches `last_saved_id + 1`.
- Any non-matching numbered patterns are safely ignored as part of the abstract/body text.

---

## 📊 Validation & Results

- **Expected Articles:** 2,535
- **Parsed Articles:** 2,535
- **Unique IDs:** 2,535
- **Gaps/Missing IDs:** None (0 missing)
- **Duplicate IDs:** None (0 duplicates)

### Sample Output Record (JSON):
```json
{
  "id": 17,
  "authors": [
    "Hochmuth, Z."
  ],
  "title": "Z činnosti oblastnej skupiny č. 12 – Ružomberok",
  "pages": "26-29",
  "extras": [
    "1 pl. j."
  ],
  "year": 1970,
  "volume": "I.",
  "issue": "2",
  "abstract": "Výskum Liskovskej jaskyne, objav jaskýň na Meškove"
}
```
All parsed items are clean and ready for Zotero upload.
