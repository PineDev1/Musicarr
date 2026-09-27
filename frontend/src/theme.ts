export type ThemeChoice = 'dark' | 'light' | 'system'
export type AccentChoice = 'green' | 'blue' | 'purple' | 'amber'

const THEME_KEY = 'musicarr-theme'
const ACCENT_KEY = 'musicarr-accent'

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    /* ignore — private browsing / blocked storage */
  }
}

export function getTheme(): ThemeChoice {
  const v = safeGet(THEME_KEY)
  return v === 'dark' || v === 'light' || v === 'system' ? v : 'dark'
}

export function getAccent(): AccentChoice {
  const v = safeGet(ACCENT_KEY)
  return v === 'blue' || v === 'purple' || v === 'amber' ? v : 'green'
}

function resolveTheme(choice: ThemeChoice): 'dark' | 'light' {
  if (choice === 'system') {
    try {
      return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
    } catch {
      return 'dark'
    }
  }
  return choice
}

export function applyTheme(): void {
  const resolved = resolveTheme(getTheme())
  document.documentElement.setAttribute('data-theme', resolved)
  const accent = getAccent()
  if (accent === 'green') {
    document.documentElement.removeAttribute('data-accent')
  } else {
    document.documentElement.setAttribute('data-accent', accent)
  }
}

export function setTheme(choice: ThemeChoice): void {
  safeSet(THEME_KEY, choice)
  applyTheme()
}

export function setAccent(choice: AccentChoice): void {
  safeSet(ACCENT_KEY, choice)
  applyTheme()
}
