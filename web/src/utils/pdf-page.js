const DEFAULT_PDF_PAGE_OFFSET = 2;

function normalizedPdfUrl(value) {
  return String(value || '').trim().split(/[?#]/, 1)[0];
}

function printedPage(article) {
  const match = String(article.pages || '').match(/^\s*(\d+)/);
  return match ? Number(match[1]) : null;
}

function explicitOffset(article) {
  if (article.pdf_page_offset === null || article.pdf_page_offset === undefined || article.pdf_page_offset === '') {
    return null;
  }
  const offset = Number(article.pdf_page_offset);
  return Number.isFinite(offset) ? offset : null;
}

export function getPdfPageNumber(article, issueOffsets = {}) {
  const start = printedPage(article);
  const journalId = article.journal_id || 'spravodaj_sss';

  if (journalId === 'spravodaj_sss') {
    const physicalStart = Number(article.pdf_page_start);
    const articleOffset = explicitOffset(article);
    if (Number.isFinite(physicalStart) && article.pdf_page_start !== null && article.pdf_page_start !== undefined && articleOffset !== null) {
      return physicalStart + articleOffset;
    }
    if (start === null) {
      return Number.isFinite(physicalStart) && physicalStart > 0 ? physicalStart : 1;
    }
    const mapping = issueOffsets[normalizedPdfUrl(article.pdf_url)] ?? DEFAULT_PDF_PAGE_OFFSET;
    if (articleOffset !== null) return start + articleOffset;
    if (typeof mapping === 'number') return start + mapping;
    let offset = mapping.article_offsets?.[String(article.id)] ?? mapping.offset;
    for (const range of mapping.ranges ?? []) {
      if (start >= range.from) offset = range.offset;
    }
    return Math.floor(start / (mapping.divisor ?? 1)) + offset;
  }

  const pageStart = Number(article.pdf_page_start || start || 1);
  return pageStart + (explicitOffset(article) ?? DEFAULT_PDF_PAGE_OFFSET);
}
