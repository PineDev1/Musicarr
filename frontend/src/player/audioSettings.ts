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
const PRESETS_KEY = 'musicarr-eq-presets-v1'

function loadCustomPresets(): Record<string, number[]> {
  try {
    const raw = JSON.parse(localStorage.getItem(PRESETS_KEY) || '{}')
    const out: Record<string, number[]> = {}
    for (const [k, v] of Object.entries(raw)) {
      if (Array.isArray(v) && v.length === EQ_BANDS.length) {
        out[k] = v.map((b) => clamp(Number(b) || 0, -12, 12))
      }
    }
    return out
  } catch {
    return {}
  }
}

let customPresets = loadCustomPresets()

export function saveCustomPreset(name: string, bands: number[]) {
  const n = name.trim().slice(0, 40)
  if (!n || n in EQ_PRESETS) return
  customPresets = { ...customPresets, [n]: bands.slice() }
  persistPresets()
}

export function deleteCustomPreset(name: string) {
  const { [name]: _removed, ...rest } = customPresets
  customPresets = rest
  persistPresets()
}

function persistPresets() {
  try {
    localStorage.setItem(PRESETS_KEY, JSON.stringify(customPresets))
  } catch {
    /* storage unavailable */
  }
  listeners.forEach((l) => l())
}

export function getCustomPresets() {
  return customPresets
}

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

export function useCustomPresets() {
  return useSyncExternalStore(subscribeAudioSettings, getCustomPresets, getCustomPresets)
}
