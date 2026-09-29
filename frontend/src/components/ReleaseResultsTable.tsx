import type { IndexerSearchError, ReleaseCandidate } from '../api'

export function ReleaseResultsTable({
  results,
  errors,
  isLoading,
  error,
  onGrab,
  grabPending,
  showAlbumBadge = false,
}: {
  results: ReleaseCandidate[] | undefined
  errors: IndexerSearchError[] | undefined
  isLoading: boolean
  error: Error | null
  onGrab: (release: ReleaseCandidate) => void
  grabPending: boolean
  // Artist-level search mixes releases across every album — show which
  // album each one resolves to (or "New release" when unmatched).
  showAlbumBadge?: boolean
}) {
  if (isLoading) return <p className="muted">Searching indexers…</p>
  if (error) return <p className="error">{error.message}</p>

  return (
    <>
      {!!errors?.length && (
        <div className="banner danger" style={{ marginBottom: '0.75rem' }}>
          <strong>Some indexers failed to search:</strong>
          <ul style={{ margin: '0.5rem 0 0', paddingLeft: '1.2rem' }}>
            {errors.map((e) => (
              <li key={e.indexer_id}>
                {e.indexer_name}: {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {results && results.length === 0 && !errors?.length && (
        <p className="muted">No results. Add or check your indexers under Settings → Indexers.</p>
      )}
      {!!results?.length && (
        <table className="table">
          <thead>
            <tr>
              <th>Release</th>
              {showAlbumBadge && <th>Album</th>}
              <th>Indexer</th>
              <th>Size</th>
              <th>Seeders</th>
              <th>Score</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {results.map((r, i) => (
              <tr key={`${r.indexer_id}-${i}`}>
                <td style={{ maxWidth: 420, wordBreak: 'break-word' }}>
                  {r.title}
                  {r.blocklisted && (
                    <span
                      className="badge failed"
                      style={{ marginLeft: 8 }}
                      title="Failed or rejected before — auto-grab skips this release"
                    >
                      Blocklisted
                    </span>
                  )}
                </td>
                {showAlbumBadge && (
                  <td>
                    {r.matched_album_id != null ? (
                      <span className="badge queued">{r.matched_album_title}</span>
                    ) : (
                      <span className="badge wanted">New release</span>
                    )}
                  </td>
                )}
                <td className="muted">{r.indexer_name}</td>
                <td className="muted">{r.size ? `${(r.size / (1024 * 1024)).toFixed(0)} MB` : '—'}</td>
                <td className="muted">{r.protocol === 'torrent' ? r.seeders : '—'}</td>
                <td>
                  <span className={`badge ${r.score >= 10 ? 'queued' : 'skipped'}`}>
                    {r.score.toFixed(1)}
                  </span>
                </td>
                <td className="row-actions">
                  <button
                    type="button"
                    className="btn ghost"
                    disabled={grabPending}
                    onClick={() => onGrab(r)}
                  >
                    Grab
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  )
}
