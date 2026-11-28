import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';

import { getPdfPageNumber, getPdfPageLink, withReviewPdfLinks } from '../src/utils/pdf-page.js';

test('review links use the same article and issue offsets as the main page', () => {
  const offsets = JSON.parse(readFileSync(new URL('../src/data/pdf_page_offsets.json', import.meta.url), 'utf8'));
  const article = {
    id: 711, pages: '29', pdf_page_start: 29,
    pdf_url: 'https://sss.sk/wp-content/uploads/2022/03/Spravodaj_SSS_1-2_1985.pdf',
  };
  const incident = { id: 711, pdf_links: [{ page: 29, url: `${article.pdf_url}#page=29` }] };
  const resolved = withReviewPdfLinks(incident, article, offsets);
  assert.deepEqual(resolved.pdf_links, [{ page: 31, url: `${article.pdf_url}#page=31` }]);
  assert.equal(incident.pdf_links[0].page, 29);
  assert.deepEqual(withReviewPdfLinks(incident, null, offsets), incident);
  assert.deepEqual(withReviewPdfLinks(incident, { id: 711 }, offsets).pdf_links, []);
});

test('review and cave links preserve special page mappings and missing PDFs', () => {
  const offsets = JSON.parse(readFileSync(new URL('../src/data/pdf_page_offsets.json', import.meta.url), 'utf8'));
  const article = {
    id: 2814, pages: '82', pdf_url: 'https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf',
  };
  assert.deepEqual(getPdfPageLink(article, offsets), { page: 45, url: `${article.pdf_url}#page=45` });
  assert.equal(getPdfPageLink({ id: 1 }, offsets), null);
});

test('links the verified Slovenský kras double-page spreads', () => {
  const articles = JSON.parse(readFileSync(new URL('../src/data/articles.json', import.meta.url), 'utf8'));
  for (const [id, page] of [[4996, 32], [5001, 30], [5002, 47]]) {
    assert.equal(getPdfPageNumber(articles.find((article) => article.id === id)), page);
  }
});

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

test('links cover pages and two-page spreads to their physical PDF pages', () => {
  const offsets = JSON.parse(readFileSync(new URL('../src/data/pdf_page_offsets.json', import.meta.url), 'utf8'));
  const cases = [
    ['https://sss.sk/wp-content/uploads/2022/03/Spravodaj_SSS_1-2_1985.pdf', '1', 3],
    ['https://sss.sk/wp-content/uploads/2022/03/Spravodaj_SSS_1-2_1985.pdf', '3-7', 5],
    ['https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf', '4', 5],
    ['https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf', '45', 25],
    ['https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf', '65', 35],
    ['https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf', '82', 44],
  ];

  for (const [pdf_url, pages, expected] of cases) {
    assert.equal(getPdfPageNumber({ pdf_url, pages }, offsets), expected);
  }
});

test('links across inserted pages, omitted pages and an appendix', () => {
  const offsets = JSON.parse(readFileSync(new URL('../src/data/pdf_page_offsets.json', import.meta.url), 'utf8'));
  const cases = [
    ['https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2010-2.pdf', '30', undefined, 32],
    ['https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2010-2.pdf', '31', undefined, 35],
    ['https://sss.sk/wp-content/uploads/2017/10/772.pdf', '20', undefined, 11],
    ['https://sss.sk/wp-content/uploads/2017/10/772.pdf', '21', undefined, 15],
    ['https://sss.sk/wp-content/uploads/2017/10/772.pdf', '25', undefined, 17],
    ['https://sss.sk/wp-content/uploads/2017/10/772.pdf', '35', undefined, 22],
    ['https://sss.sk/wp-content/uploads/2011/10/Spravodaj-2012-1.pdf', '82', 2814, 45],
    ['https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf', '11', undefined, 10],
    ['https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf', '35', undefined, 32],
    ['https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf', '67', undefined, 63],
    ['https://sss.sk/wp-content/uploads/2021/12/Spravodaj_2_1979.pdf', '79', undefined, 73],
    ['https://sss.sk/wp-content/uploads/2022/02/Spravodaj_SSS_1983_1.pdf', '1', 553, 3],
    ['https://sss.sk/wp-content/uploads/2022/02/Spravodaj_SSS_1983_1.pdf', '1', 569, 45],
  ];
  for (const [pdf_url, pages, id, expected] of cases) {
    assert.equal(getPdfPageNumber({ pdf_url, pages, id }, offsets), expected);
  }
});

test('links the Slovensky kras article to its physical start', () => {
  const articles = JSON.parse(readFileSync(new URL('../src/data/articles.json', import.meta.url), 'utf8'));
  assert.equal(getPdfPageNumber(articles.find((article) => article.id === 5702)), 108);
});

test('links corrected articles to their verified physical starts', () => {
  const articles = JSON.parse(readFileSync(new URL('../src/data/articles.json', import.meta.url), 'utf8'));
  const offsets = JSON.parse(readFileSync(new URL('../src/data/pdf_page_offsets.json', import.meta.url), 'utf8'));
  for (const [id, page] of [[1502, 31], [2814, 45], [3993, 5], [3994, 8], [4133, 1], [4134, 4], [4135, 10], [4136, 19]]) {
    assert.equal(getPdfPageNumber(articles.find((article) => article.id === id), offsets), page);
  }
});
