import assert from 'node:assert/strict';
import test from 'node:test';

import { getPdfPageNumber } from '../src/utils/pdf-page.js';

test('uses the PDF issue offset for Spravodaj printed pages', () => {
  const offsets = {
    'https://sss.sk/wp-content/uploads/2017/10/723.pdf': 1,
    'https://sss.sk/wp-content/uploads/2022/05/Spravodaj_SSS_4_1998.pdf': 2,
    'https://sss.sk/wp-content/uploads/2020/01/spravodaj2018_1.pdf': 2,
  };

  assert.equal(getPdfPageNumber({
    journal_id: 'spravodaj_sss',
    pages: '3-9',
    pdf_page_start: 4,
    pdf_url: 'https://sss.sk/wp-content/uploads/2017/10/723.pdf',
  }, offsets), 4);
  assert.equal(getPdfPageNumber({
    journal_id: 'spravodaj_sss',
    pages: '4-6',
    pdf_page_start: 6,
    pdf_url: 'https://sss.sk/wp-content/uploads/2022/05/Spravodaj_SSS_4_1998.pdf',
  }, offsets), 6);
  assert.equal(getPdfPageNumber({
    journal_id: 'spravodaj_sss',
    pages: '4-6',
    pdf_page_start: 4,
    pdf_url: 'https://sss.sk/wp-content/uploads/2020/01/spravodaj2018_1.pdf',
  }, offsets), 6);
});

test('preserves physical page numbers and offsets for other journals', () => {
  assert.equal(getPdfPageNumber({
    journal_id: 'aragonit',
    pages: '51-60',
    pdf_page_start: 5,
    pdf_page_offset: 0,
  }), 5);
});
