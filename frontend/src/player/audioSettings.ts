import { useSyncExternalStore } from 'react'

export const EQ_BANDS = [60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000] as const

export type AudioSettings = {
  eqEnabled: boolean
  preampDb: number
  bandsDb: number[]
  speed: number
  crossfadeMs: number
}

export const EQ_PRESETS: Record<string, number[]> = {
  Flat: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  'Bass boost': [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
  'Treble boost': [0, 0, 0, 0, 0, 1, 3, 5, 6, 6],
  Vocal: [-2, -1, 0, 2, 4, 4, 2, 0, -1, -2],
  Rock: [4, 3, 1, -1, -2, 0, 2, 3, 4, 4],
  Electronic: [5, 4, 1, 0, -2, 2, 1, 2, 4, 5],
}

const KEY = 'musicarr-audio-settings-v1'

export const DEFAULT_AUDIO_SETTINGS: AudioSettings = {
  eqEnabled: false,
  preampDb: 0,
  bandsDb: EQ_PRESETS.Flat,
  speed: 1,
  crossfadeMs: 700,
}

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n))
}

function sanitize(raw: Partial<AudioSettings> | null): AudioSettings {
  const d = DEFAULT_AUDIO_SETTINGS
  if (!raw) return d
  const bands =
    Array.isArray(raw.bandsDb) && raw.bandsDb.length === EQ_BANDS.length
      ? raw.bandsDb.map((b) => clamp(Number(b) || 0, -12, 12))
      : d.bandsDb
  return {
    eqEnabled: !!raw.eqEnabled,
    preampDb: clamp(Number(raw.preampDb) || 0, -12, 12),
    bandsDb: bands,
    speed: clamp(Number(raw.speed) || 1, 0.5, 2),
    crossfadeMs: clamp(Number(raw.crossfadeMs) || d.crossfadeMs, 200, 12000),
  }
}

function load(): AudioSettings {
  try {
    const s = localStorage.getItem(KEY)
    return sanitize(s ? JSON.parse(s) : null)
  } catch {
    return DEFAULT_AUDIO_SETTINGS
  }
}

let current = load()
const listeners = new Set<() => void>()

export function getAudioSettings() {
  return current
}

export function updateAudioSettings(patch: Partial<AudioSettings>) {
  current = sanitize({ ...current, ...patch })
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l())
}

export function subscribeAudioSettings(fn: () => void) {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

export function useAudioSettings() {
  return useSyncExternalStore(subscribeAudioSettings, getAudioSettings, getAudioSettings)
}
