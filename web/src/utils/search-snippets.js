function fold(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('sk');
}

export function normalizeSearchText(value) {
  return fold(value).trim();
}

export function makeSearchSnippet(text, query) {
  const source = String(text || '').replace(/\s+/g, ' ').trim();
  if (!source) return '';

  let normalized = '';
  const positions = [];
  let offset = 0;
  for (const char of source) {
    const part = fold(char);
    normalized += part;
    for (let i = 0; i < part.length; i++) positions.push(offset);
    offset += char.length;
  }

  const matches = normalizeSearchText(query).split(/\s+/)
    .filter(Boolean)
    .map((term) => normalized.indexOf(term))
    .filter((index) => index >= 0);
  const at = matches.length ? positions[Math.min(...matches)] : 0;
  const start = Math.max(0, at - 110);
  const end = Math.min(source.length, at + 220);
  return `${start ? '… ' : ''}${source.slice(start, end).trim()}${end < source.length ? ' …' : ''}`;
}
