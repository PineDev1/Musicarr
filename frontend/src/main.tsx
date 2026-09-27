import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { applyTheme, getTheme } from './theme'

// Apply before the first paint so there's no flash of the wrong theme.
applyTheme()
if (getTheme() === 'system') {
  try {
    window
      .matchMedia('(prefers-color-scheme: light)')
      .addEventListener('change', applyTheme)
  } catch {
    /* matchMedia unsupported */
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
