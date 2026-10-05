const KEY = 'musicarr-device-id'

export function getDeviceId(): string {
  try {
    let id = localStorage.getItem(KEY)
    if (!id) {
      id =
        typeof crypto !== 'undefined' && 'randomUUID' in crypto
          ? crypto.randomUUID()
          : `dev-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`
      localStorage.setItem(KEY, id)
    }
    return id
  } catch {
    return 'unknown-device'
  }
}

/** Human-friendly label like "Chrome on Mac", shown on the other device's banner. */
export function getDeviceName(): string {
  const ua = navigator.userAgent
  const browser = /Edg\//.test(ua)
    ? 'Edge'
    : /Firefox\//.test(ua)
      ? 'Firefox'
      : /Chrome\//.test(ua)
        ? 'Chrome'
        : /Safari\//.test(ua)
          ? 'Safari'
          : 'Browser'
  const os = /iPhone|iPad|iPod/.test(ua)
    ? 'iOS'
    : /Android/.test(ua)
      ? 'Android'
      : /Mac OS X/.test(ua)
        ? 'Mac'
        : /Windows/.test(ua)
          ? 'Windows'
          : /Linux/.test(ua)
            ? 'Linux'
            : 'device'
  return `${browser} on ${os}`
}
