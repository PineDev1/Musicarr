import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api, type ArtistSearchResult, type BulkArtistSearchResult } from '../api'
import { useToast } from '../Toast'

export function AddArtistPage() {
  const [searchParams] = useSearchParams()
  const qFromUrl = searchParams.get('q') || ''
  const [q, setQ] = useState(qFromUrl)
  const [submitted, setSubmitted] = useState(qFromUrl)
  const [bulkText, setBulkText] = useState('')
  const [bulkMode, setBulkMode] = useState(false)
  const [bulkResults, setBulkResults] = useState<BulkArtistSearchResult[] | null>(null)
  const [picks, setPicks] = useState<Record<string, ArtistSearchResult>>({})
  const [includeSingles, setIncludeSingles] = useState(false)
  const [monitorMode, setMonitorMode] = useState<'all' | 'new' | 'none'>('all')
  const [downloadMode, setDownloadMode] = useState<'' | 'auto' | 'manual'>('')
  const [confirming, setConfirming] = useState<ArtistSearchResult | null>(null)
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()

  const search = useQuery({
    queryKey: ['search', submitted],
    queryFn: () => api.searchArtists(submitted),
    enabled: submitted.length > 0 && !bulkMode,
  })

  const add = useMutation({
    mutationFn: (payload: { provider_id: string; provider: string }) =>
      api.addArtist(payload.provider_id, payload.provider, {
        include_singles: includeSingles,
        download_missing: true,
        monitor_mode: monitorMode,
        download_mode: downloadMode || null,
      }),
    onSuccess: (artist) => {
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push(`Added ${artist.name}`, 'ok')
      setConfirming(null)
      navigate(`/artists/${artist.id}`)
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const bulkSearch = useMutation({
    mutationFn: () => api.bulkSearchArtists(bulkText),
    onSuccess: (rows) => {
      setBulkResults(rows)
      const next: Record<string, ArtistSearchResult> = {}
      for (const row of rows) {
        if (row.results[0]) next[row.query] = row.results[0]
      }
      setPicks(next)
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  const bulkAdd = useMutation({
    mutationFn: async () => {
      const selected = Object.values(picks)
      let added = 0
      for (const hit of selected) {
        await api.addArtist(hit.provider_id, hit.provider, {
          include_singles: includeSingles,
          download_missing: true,
          monitor_mode: monitorMode,
          download_mode: downloadMode || null,
        })
        added += 1
      }
      return added
    },
    onSuccess: (added) => {
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push(`Added ${added} artist(s)`, 'ok')
      setBulkResults(null)
      setBulkText('')
      setPicks({})
      navigate('/')
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitted(q.trim())
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Add Artist</h1>
          <p>
            Search your active provider, add an artist, and download MusicBrainz-matched releases.
          </p>
        </div>
        <button
          type="button"
          className="btn secondary"
          onClick={() => {
            setBulkMode((v) => !v)
            setBulkResults(null)
            setSubmitted('')
          }}
        >
          {bulkMode ? 'Single search' : 'Paste a list'}
        </button>
      </div>

      {!bulkMode ? (
        <>
          <form className="toolbar" onSubmit={onSubmit} style={{ flexWrap: 'wrap' }}>
            <input
              type="text"
              placeholder="Search artists…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ flex: 1, minWidth: 200 }}
            />
            <button className="btn" type="submit" disabled={!q.trim()}>
              Search
            </button>
            <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={includeSingles}
                onChange={(e) => setIncludeSingles(e.target.checked)}
              />
              Include singles (MusicBrainz-matched)
            </label>
          </form>

          {search.isFetching && <p className="muted">Searching…</p>}
          {search.error && <p className="error">{(search.error as Error).message}</p>}

          {confirming && (
            <div className="album-row" style={{ marginBottom: '1rem', alignItems: 'flex-start' }}>
              {confirming.image_url ? (
                <img src={confirming.image_url} alt="" />
              ) : (
                <div className="placeholder-art" style={{ width: 64, height: 64 }} />
              )}
              <div className="grow">
                <div>
                  <strong>{confirming.name}</strong>{' '}
                  <span className="badge queued">{confirming.provider}</span>
                </div>
                <div className="muted" style={{ marginBottom: 8 }}>
                  {confirming.nb_album != null ? `${confirming.nb_album} releases on ${confirming.provider}` : ''}
                </div>
                <div className="toolbar" style={{ flexWrap: 'wrap', marginBottom: 0 }}>
                  <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    Monitor
                    <select
                      value={monitorMode}
                      onChange={(e) => setMonitorMode(e.target.value as 'all' | 'new' | 'none')}
                    >
                      <option value="all">All albums</option>
                      <option value="new">New releases only</option>
                      <option value="none">Don't monitor</option>
                    </select>
                  </label>
                  <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    Downloads
                    <select
                      value={downloadMode}
                      onChange={(e) => setDownloadMode(e.target.value as '' | 'auto' | 'manual')}
                    >
                      <option value="">Use default</option>
                      <option value="auto">Auto-download</option>
                      <option value="manual">Manual approval</option>
                    </select>
                  </label>
                  <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input
                      type="checkbox"
                      checked={includeSingles}
                      onChange={(e) => setIncludeSingles(e.target.checked)}
                    />
                    Include singles
                  </label>
                </div>
              </div>
              <div className="row-actions">
                <button
                  className="btn"
                  disabled={add.isPending}
                  onClick={() =>
                    add.mutate({ provider_id: confirming.provider_id, provider: confirming.provider })
                  }
                >
                  {add.isPending ? 'Adding…' : 'Confirm & Add'}
                </button>
                <button className="btn ghost" onClick={() => setConfirming(null)}>
                  Back
                </button>
              </div>
            </div>
          )}

          {search.data && !confirming && (
            <div className="search-results">
              {search.data.map((a, i) => (
                <motion.div
                  key={`${a.provider}-${a.provider_id}`}
                  className="search-row"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i * 0.03, 0.3) }}
                >
                  {a.image_url ? (
                    <img src={a.image_url} alt="" />
                  ) : (
                    <div className="placeholder-art" style={{ width: 56, height: 56 }} />
                  )}
                  <div className="grow">
                    <strong>{a.name}</strong>
                    <div className="muted">
                      <span className="badge queued">{a.provider}</span>{' '}
                      {a.nb_album != null ? `${a.nb_album} releases` : ''}
                    </div>
                  </div>
                  <button className="btn" onClick={() => setConfirming(a)}>
                    Add
                  </button>
                </motion.div>
              ))}
              {search.data.length === 0 && <p className="muted">No artists found.</p>}
            </div>
          )}
        </>
      ) : (
        <>
          <p className="muted">Paste one artist name per line (up to 40).</p>
          <textarea
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            rows={8}
            style={{ width: '100%', marginBottom: '0.75rem' }}
            placeholder={'Daft Punk\nRadiohead\nBjörk'}
          />
          <div className="toolbar" style={{ flexWrap: 'wrap' }}>
            <button
              className="btn"
              type="button"
              disabled={!bulkText.trim() || bulkSearch.isPending}
              onClick={() => bulkSearch.mutate()}
            >
              {bulkSearch.isPending ? 'Searching…' : 'Search all'}
            </button>
            <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={includeSingles}
                onChange={(e) => setIncludeSingles(e.target.checked)}
              />
              Include singles
            </label>
            <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              Monitor
              <select
                value={monitorMode}
                onChange={(e) => setMonitorMode(e.target.value as 'all' | 'new' | 'none')}
              >
                <option value="all">All albums</option>
                <option value="new">New releases only</option>
                <option value="none">Don't monitor</option>
              </select>
            </label>
            <label className="muted" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              Downloads
              <select
                value={downloadMode}
                onChange={(e) => setDownloadMode(e.target.value as '' | 'auto' | 'manual')}
              >
                <option value="">Use default</option>
                <option value="auto">Auto-download</option>
                <option value="manual">Manual approval</option>
              </select>
            </label>
            {bulkResults && Object.keys(picks).length > 0 && (
              <button
                className="btn"
                type="button"
                disabled={bulkAdd.isPending}
                onClick={() => bulkAdd.mutate()}
              >
                {bulkAdd.isPending
                  ? 'Adding…'
                  : `Add selected (${Object.keys(picks).length})`}
              </button>
            )}
          </div>

          {bulkResults && (
            <div className="search-results" style={{ marginTop: '1rem' }}>
              {bulkResults.map((row) => (
                <div key={row.query} style={{ marginBottom: '1rem' }}>
                  <strong>{row.query}</strong>
                  {row.error && <p className="error">{row.error}</p>}
                  {!row.error && row.results.length === 0 && (
                    <p className="muted">No matches</p>
                  )}
                  {row.results.map((a) => {
                    const key = row.query
                    const picked = picks[key]
                    const isPick =
                      picked?.provider_id === a.provider_id && picked?.provider === a.provider
                    return (
                      <div key={`${a.provider}-${a.provider_id}`} className="search-row">
                        {a.image_url ? (
                          <img src={a.image_url} alt="" />
                        ) : (
                          <div className="placeholder-art" style={{ width: 56, height: 56 }} />
                        )}
                        <div className="grow">
                          <strong>{a.name}</strong>
                          <div className="muted">
                            <span className="badge queued">{a.provider}</span>{' '}
                            {a.nb_album != null ? `${a.nb_album} releases` : ''}
                          </div>
                        </div>
                        <button
                          className={isPick ? 'btn' : 'btn ghost'}
                          type="button"
                          onClick={() =>
                            setPicks((prev) => {
                              const next = { ...prev }
                              if (isPick) delete next[key]
                              else next[key] = a
                              return next
                            })
                          }
                        >
                          {isPick ? 'Selected' : 'Select'}
                        </button>
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
