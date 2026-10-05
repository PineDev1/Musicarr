import { lazy, type ComponentType } from 'react'

const RELOAD_KEY = 'musicarr-chunk-reload'

/**
 * React.lazy for route chunks that survives deploys. A tab opened before an
 * update still asks for chunk hashes that no longer exist; that import fails
 * and the page would stay broken until a manual refresh. On the first such
 * failure we reload once (the fresh index.html points at the new chunks); the
 * sessionStorage flag stops a reload loop if the failure is something else.
 */
export function lazyPage<T extends ComponentType<any>>(load: () => Promise<{ default: T }>) {
  return lazy(async () => {
    try {
      const mod = await load()
      try {
        sessionStorage.removeItem(RELOAD_KEY)
      } catch {
        /* storage unavailable */
      }
      return mod
    } catch (err) {
      let alreadyReloaded = true
      try {
        alreadyReloaded = sessionStorage.getItem(RELOAD_KEY) === '1'
        if (!alreadyReloaded) sessionStorage.setItem(RELOAD_KEY, '1')
      } catch {
        /* storage unavailable: don't risk a reload loop */
      }
      if (!alreadyReloaded) {
        window.location.reload()
        return new Promise<never>(() => undefined) // page is going away
      }
      throw err
    }
  })
}
