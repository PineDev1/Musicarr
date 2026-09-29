import { useState } from 'react'
import {
  EQ_BANDS,
  deleteCustomPreset,
  saveCustomPreset,
  useCustomPresets,
  EQ_PRESETS,
  updateAudioSettings,
  useAudioSettings,
} from './audioSettings'

const SPEEDS = [0.75, 1, 1.25, 1.5, 2]

function bandLabel(f: number) {
  return f >= 1000 ? `${f / 1000}k` : String(f)
}

export function AudioSettingsPanel() {
  const s = useAudioSettings()
  const custom = useCustomPresets()
  const [presetName, setPresetName] = useState('')
  return (
    <div className="audio-settings">
      <div className="section-label">Audio</div>

      <div className="audio-row">
        <span className="muted tiny">Speed</span>
        <div className="sleep-options">
          {SPEEDS.map((v) => (
            <button
              key={v}
              type="button"
              className={`btn ghost${s.speed === v ? ' active' : ''}`}
              onClick={() => updateAudioSettings({ speed: v })}
            >
              {v}x
            </button>
          ))}
        </div>
      </div>

      <label className="audio-row">
        <span className="muted tiny">Crossfade length: {(s.crossfadeMs / 1000).toFixed(1)}s</span>
        <input
          type="range"
          min={200}
          max={12000}
          step={100}
          value={s.crossfadeMs}
          onChange={(e) => updateAudioSettings({ crossfadeMs: Number(e.target.value) })}
        />
        <span className="muted tiny">Applies when crossfade is enabled in player settings.</span>
      </label>

      <div className="audio-row">
        <label className="audio-toggle">
          <input
            type="checkbox"
            checked={s.eqEnabled}
            onChange={(e) => updateAudioSettings({ eqEnabled: e.target.checked })}
          />
          <span>Equalizer</span>
        </label>
        <div className="sleep-options">
          {Object.entries(EQ_PRESETS).map(([name, bands]) => (
            <button
              key={name}
              type="button"
              className="btn ghost"
              onClick={() => updateAudioSettings({ eqEnabled: true, bandsDb: bands })}
            >
              {name}
            </button>
          ))}
        </div>
        {Object.keys(custom).length > 0 && (
          <div className="sleep-options">
            {Object.entries(custom).map(([name, bands]) => (
              <span key={name} className="eq-custom-preset">
                <button
                  type="button"
                  className="btn ghost"
                  onClick={() => updateAudioSettings({ eqEnabled: true, bandsDb: bands })}
                >
                  {name}
                </button>
                <button
                  type="button"
                  className="btn ghost danger"
                  aria-label={`Delete preset ${name}`}
                  onClick={() => deleteCustomPreset(name)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="eq-save">
          <input
            type="text"
            placeholder="Save current curve as preset…"
            value={presetName}
            maxLength={40}
            onChange={(e) => setPresetName(e.target.value)}
          />
          <button
            type="button"
            className="btn ghost"
            disabled={!presetName.trim() || presetName.trim() in EQ_PRESETS}
            onClick={() => {
              saveCustomPreset(presetName, s.bandsDb)
              setPresetName('')
            }}
          >
            Save
          </button>
        </div>
        <label className="audio-row">
          <span className="muted tiny">Preamp {s.preampDb > 0 ? '+' : ''}{s.preampDb} dB</span>
          <input
            type="range"
            min={-12}
            max={12}
            step={1}
            value={s.preampDb}
            onChange={(e) => updateAudioSettings({ preampDb: Number(e.target.value) })}
          />
        </label>
        <div className="eq-bands">
          {EQ_BANDS.map((f, i) => (
            <label key={f} className="eq-band">
              <input
                type="range"
                min={-12}
                max={12}
                step={1}
                value={s.bandsDb[i]}
                onChange={(e) => {
                  const bands = [...s.bandsDb]
                  bands[i] = Number(e.target.value)
                  updateAudioSettings({ bandsDb: bands })
                }}
              />
              <span className="muted tiny">{bandLabel(f)}</span>
            </label>
          ))}
        </div>
      </div>
    </div>
  )
}
