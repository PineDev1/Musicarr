import { useEffect, useRef } from 'react'

export type WavePrefs = {
  wave_height: number
  wave_length: number
  wave_speed: number
  wave_thickness: number
  wave_color: string
  wave_flatten_when_paused: boolean
}

type Props = {
  value: number
  max: number
  playing: boolean
  prefs: WavePrefs
  onSeek: (t: number) => void
  className?: string
}

/** Android 13–style squiggly seek bar (inspired by mahozad/wavy-slider). */
export function WavySeekBar({ value, max, playing, prefs, onSeek, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const dragRef = useRef(false)
  const phaseRef = useRef(0)
  const heightAnimRef = useRef(prefs.wave_height)
  const valueRef = useRef(value)
  const maxRef = useRef(max)
  const playingRef = useRef(playing)
  const prefsRef = useRef(prefs)
  const onSeekRef = useRef(onSeek)

  valueRef.current = value
  maxRef.current = max
  playingRef.current = playing
  prefsRef.current = prefs
  onSeekRef.current = onSeek

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    let raf = 0
    let last = performance.now()

    const draw = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const p = prefsRef.current
      const targetH =
        playingRef.current || !p.wave_flatten_when_paused ? p.wave_height : 0
      heightAnimRef.current += (targetH - heightAnimRef.current) * Math.min(1, dt * 8)
      phaseRef.current += p.wave_speed * dt

      const dpr = window.devicePixelRatio || 1
      const cssW = canvas.clientWidth || 280
      const cssH = canvas.clientHeight || 28
      if (canvas.width !== Math.floor(cssW * dpr) || canvas.height !== Math.floor(cssH * dpr)) {
        canvas.width = Math.floor(cssW * dpr)
        canvas.height = Math.floor(cssH * dpr)
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, cssW, cssH)

      const mid = cssH / 2
      const progress =
        maxRef.current > 0 ? Math.min(1, Math.max(0, valueRef.current / maxRef.current)) : 0
      const thumbX = progress * cssW
      const amp = heightAnimRef.current
      const wl = Math.max(4, p.wave_length)
      const thick = Math.max(1, p.wave_thickness)
      const color = p.wave_color || '#3dba7a'
      const muted = 'rgba(255,255,255,0.28)'

      const drawWave = (from: number, to: number, stroke: string, wavy: boolean) => {
        if (to <= from) return
        ctx.beginPath()
        ctx.lineWidth = thick
        ctx.lineCap = 'round'
        ctx.strokeStyle = stroke
        const step = 2
        for (let x = from; x <= to; x += step) {
          const y = wavy && amp > 0.15
            ? mid + Math.sin((x + phaseRef.current) * ((Math.PI * 2) / wl)) * amp
            : mid
          if (x === from) ctx.moveTo(x, y)
          else ctx.lineTo(x, y)
        }
        ctx.stroke()
      }

      drawWave(0, thumbX, color, true)
      drawWave(thumbX, cssW, muted, false)

      ctx.beginPath()
      ctx.fillStyle = '#fff'
      ctx.arc(thumbX, mid, Math.max(5, thick + 3), 0, Math.PI * 2)
      ctx.fill()
      ctx.beginPath()
      ctx.fillStyle = color
      ctx.arc(thumbX, mid, Math.max(3, thick + 1), 0, Math.PI * 2)
      ctx.fill()

      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [])

  function posFromEvent(clientX: number) {
    const canvas = canvasRef.current
    if (!canvas) return 0
    const rect = canvas.getBoundingClientRect()
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
    return ratio * (maxRef.current || 0)
  }

  return (
    <canvas
      ref={canvasRef}
      className={className || 'wavy-seek'}
      height={28}
      role="slider"
      aria-valuemin={0}
      aria-valuemax={max || 0}
      aria-valuenow={value}
      tabIndex={0}
      onPointerDown={(e) => {
        dragRef.current = true
        e.currentTarget.setPointerCapture(e.pointerId)
        onSeekRef.current(posFromEvent(e.clientX))
      }}
      onPointerMove={(e) => {
        if (!dragRef.current) return
        onSeekRef.current(posFromEvent(e.clientX))
      }}
      onPointerUp={() => {
        dragRef.current = false
      }}
      onPointerCancel={() => {
        dragRef.current = false
      }}
      onKeyDown={(e) => {
        const step = Math.max(1, (maxRef.current || 0) * 0.02)
        if (e.key === 'ArrowRight') onSeekRef.current(Math.min(maxRef.current, valueRef.current + step))
        if (e.key === 'ArrowLeft') onSeekRef.current(Math.max(0, valueRef.current - step))
      }}
    />
  )
}
