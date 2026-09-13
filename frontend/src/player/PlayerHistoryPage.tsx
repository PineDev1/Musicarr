import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { useToast } from '../Toast'
import { playerApi } from './playerApi'
import { SongShelf } from './PlayerShelves'

export function PlayerHistoryPage() {
  const toast = useToast()
  const qc = useQueryClient()
  const history = useQuery({
    queryKey: ['player-history'],
    queryFn: playerApi.listenHistory,
  })

  const clear = useMutation({
    mutationFn: playerApi.clearHistory,
    onSuccess: () => {
      toast.push('Listening history cleared', 'ok')
      qc.invalidateQueries({ queryKey: ['player-history'] })
      qc.invalidateQueries({ queryKey: ['player-builtins'] })
      qc.invalidateQueries({ queryKey: ['player-continue'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div className="am-page">
      <div className="page-header">
        <div>
          <h1>Listening history</h1>
          <p className="muted">Songs you’ve played recently on this account.</p>
        </div>
        <button
          type="button"
          className="btn ghost"
          disabled={clear.isPending || !history.data?.tracks.length}
          onClick={() => {
            if (window.confirm('Clear all listening history for this account?')) clear.mutate()
          }}
        >
          Clear history
        </button>
      </div>

      {history.isLoading && <p className="muted">Loading…</p>}
      {history.error && <p className="error">{(history.error as Error).message}</p>}
      {!history.isLoading && !history.data?.tracks.length && (
        <p className="muted">
          No history yet. Play something from the <Link to="/player">home</Link> page.
        </p>
      )}
      {!!history.data?.tracks.length && (
        <SongShelf tracks={history.data.tracks} sourceLabel="Listening history" />
      )}
    </div>
  )
}
