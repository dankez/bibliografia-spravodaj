document.querySelectorAll('.copy-citation-btn').forEach((button) => {
  button.addEventListener('click', (event) => {
    const clickedButton = event.currentTarget;
    const type = clickedButton.dataset.type;
    let text = '';
    if (type === 'iso') text = document.getElementById('cite-iso')?.textContent || '';
    else if (type === 'apa') text = document.getElementById('cite-apa')?.textContent || '';
    else if (type === 'mla') text = document.getElementById('cite-mla')?.textContent || '';

    if (!text) return;

    navigator.clipboard.writeText(text).then(() => {
      const originalText = clickedButton.textContent;
      clickedButton.textContent = 'Kopírované!';
      clickedButton.classList.remove('text-belly-firebrick');
      clickedButton.classList.add('text-belly-peru');
      setTimeout(() => {
        clickedButton.textContent = originalText;
        clickedButton.classList.remove('text-belly-peru');
        clickedButton.classList.add('text-belly-firebrick');
      }, 2000);
    });
  });
});

document.querySelectorAll('.export-citation-btn').forEach((button) => {
  button.addEventListener('click', (event) => {
    const format = event.currentTarget.dataset.format;
    const dataEl = document.getElementById('citation-raw-data');
    if (!dataEl) return;

    let fileContent = '';
    let filename = '';
    let mimeType = 'text/plain';

    if (format === 'bibtex') {
      fileContent = dataEl.dataset.bibtex || '';
      filename = 'citacia.bib';
      mimeType = 'application/x-bibtex';
    } else if (format === 'ris') {
      fileContent = dataEl.dataset.ris || '';
      filename = 'citacia.ris';
      mimeType = 'application/x-research-info-systems';
    }

    if (!fileContent) return;

    const blob = new Blob([fileContent], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  });
});
