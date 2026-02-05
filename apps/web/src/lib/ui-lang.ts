export type UiLang = 'pt' | 'en';

function normalizeLang(raw: string | null | undefined): UiLang | null {
  const v = String(raw || '').trim().toLowerCase();
  if (!v) return null;
  if (v === 'pt' || v === 'pt-br' || v === 'pt_br') return 'pt';
  if (v === 'en' || v === 'en-us' || v === 'en_us' || v === 'en-gb' || v === 'en_gb') return 'en';
  if (v.startsWith('pt')) return 'pt';
  if (v.startsWith('en')) return 'en';
  return null;
}

/**
 * Resolve UI language without an i18n framework.
 *
 * Priority:
 * 1) `?ui_lang=pt|en` query param
 * 2) `navigator.languages[0]` / `navigator.language`
 * 3) `<html lang="...">`
 */
export function resolveUiLang(): UiLang {
  if (typeof window === 'undefined') return 'pt';

  try {
    const params = new URLSearchParams(window.location.search);
    const override = normalizeLang(params.get('ui_lang'));
    if (override) return override;
  } catch {
    // ignore
  }

  try {
    const nav =
      (Array.isArray(navigator.languages) && navigator.languages.length > 0
        ? navigator.languages[0]
        : navigator.language) || '';
    const fromNavigator = normalizeLang(nav);
    if (fromNavigator) return fromNavigator;
  } catch {
    // ignore
  }

  try {
    const fromDoc = normalizeLang(document.documentElement.lang);
    if (fromDoc) return fromDoc;
  } catch {
    // ignore
  }

  return 'pt';
}

