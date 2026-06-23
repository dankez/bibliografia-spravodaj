const safeTheme = (value) => (['default', 'dark'].includes(value) ? value : 'default');

function applyTheme(value) {
  const theme = safeTheme(value);
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem('sss-theme', theme);
  } catch {}
  document.querySelectorAll('[data-theme-value]').forEach((button) => {
    const active = button.dataset.themeValue === theme;
    button.dataset.active = String(active);
    button.setAttribute('aria-pressed', String(active));
  });
}

window.addEventListener('DOMContentLoaded', () => {
  applyTheme(document.documentElement.dataset.theme);
  document.querySelectorAll('[data-theme-value]').forEach((button) => {
    button.addEventListener('click', () => applyTheme(button.dataset.themeValue));
  });
});
