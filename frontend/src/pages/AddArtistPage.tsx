import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { api } from '../api'
import { useToast } from '../Toast'

export function AddArtistPage() {
  const [q, setQ] = useState('')
  const [submitted, setSubmitted] = useState('')
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()

  const search = useQuery({
    queryKey: ['search', submitted],
    queryFn: () => api.searchArtists(submitted),
    enabled: submitted.length > 0,
  })

  const add = useMutation({
    mutationFn: (payload: { provider_id: string; provider: string }) =>
      api.addArtist(payload.provider_id, payload.provider),
    onSuccess: (artist) => {
      qc.invalidateQueries({ queryKey: ['artists'] })
      qc.invalidateQueries({ queryKey: ['queue'] })
      qc.invalidateQueries({ queryKey: ['health'] })
      toast.push(`Added ${artist.name}`, 'ok')
      navigate(`/artists/${artist.id}`)
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
          <p>Search your active provider, add an artist, and download their discography.</p>
        </div>
      </div>

      <form className="toolbar" onSubmit={onSubmit}>
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
      </form>

      {search.isFetching && <p className="muted">Searching…</p>}
      {search.error && <p className="error">{(search.error as Error).message}</p>}

      {search.data && (
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
                  {a.nb_album != null ? `${a.nb_album} albums` : ''}
                </div>
              </div>
              <button
                className="btn"
                disabled={add.isPending}
                onClick={() => add.mutate({ provider_id: a.provider_id, provider: a.provider })}
              >
                {add.isPending ? 'Adding…' : 'Add'}
              </button>
            </motion.div>
          ))}
          {search.data.length === 0 && <p className="muted">No artists found.</p>}
        </div>
      )}
    </div>
  )
}
