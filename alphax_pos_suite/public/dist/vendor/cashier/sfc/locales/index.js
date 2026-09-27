import { createI18n } from 'vue-i18n'
import en from './en'
import ar from './ar'

// Locales we ship today. Adding fr/es/hi later is just dropping a new file
// here and adding the code to LOCALES.
export const LOCALES = [
  { code: 'en', label: 'English', dir: 'ltr', native: 'English' },
  { code: 'ar', label: 'Arabic',  dir: 'rtl', native: 'العربية' }
]

export function getStoredLocale() {
  const stored = localStorage.getItem('alphax_locale')
  if (stored && LOCALES.find(l => l.code === stored)) return stored
  const nav = (navigator.language || 'en').slice(0, 2)
  if (LOCALES.find(l => l.code === nav)) return nav
  return 'en'
}

export function setStoredLocale(code) {
  localStorage.setItem('alphax_locale', code)
}

export function dirFor(code) {
  return LOCALES.find(l => l.code === code)?.dir || 'ltr'
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: getStoredLocale(),
  fallbackLocale: 'en',
  messages: { en, ar },
  // Arabic uses Arabic-Indic digits in some regions but Latin digits are
  // universal in commerce; keep Latin digits for readability.
  numberFormats: {
    en: {
      currency: { style: 'currency', currency: 'USD', currencyDisplay: 'symbol' },
      decimal: { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 },
      integer: { style: 'decimal', maximumFractionDigits: 0 }
    },
    ar: {
      currency: { style: 'currency', currency: 'USD', currencyDisplay: 'symbol' },
      decimal: { style: 'decimal', minimumFractionDigits: 2, maximumFractionDigits: 2 },
      integer: { style: 'decimal', maximumFractionDigits: 0 }
    }
  }
})

// Apply <html dir> on locale change so flexbox flips, scrollbars move,
// and RTL anchored elements behave correctly.
export function applyLocale(code) {
  i18n.global.locale.value = code
  setStoredLocale(code)
  const dir = dirFor(code)
  document.documentElement.setAttribute('dir', dir)
  document.documentElement.setAttribute('lang', code)
}
