import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { playerApi } from '../player/playerApi'
import { useToast } from '../Toast'

export function NowPlayingPage() {
  const toast = useToast()
  const qc = useQueryClient()
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['admin-now-playing'],
    queryFn: playerApi.nowPlaying,
    refetchInterval: 4000,
    retry: false,
  })
  const stop = useMutation({
    mutationFn: (userId: number) => playerApi.stopListener(userId),
    onSuccess: () => {
      toast.push('Stop sent — listener will pause', 'ok')
      qc.invalidateQueries({ queryKey: ['admin-now-playing'] })
    },
    onError: (err) => toast.push((err as Error).message, 'error'),
  })

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Now Playing</h1>
          <p>Listeners currently streaming from /player. Stop force-pauses their playback.</p>
        </div>
        {isFetching && <span className="muted">Refreshing…</span>}
      </div>
      {isLoading && <p className="muted">Loading…</p>}
      {error && <p className="error">{(error as Error).message}</p>}
      {!isLoading && !error && !data?.length && (
        <p className="muted">Nobody is listening right now.</p>
      )}
      <div className="now-playing-list">
        {data?.map((row) => (
          <div key={row.user_id} className="now-playing-card">
            {row.cover_url ? (
              <img src={row.cover_url} alt="" />
            ) : (
              <div className="now-playing-ph" />
            )}
            <div className="now-playing-meta">
              <strong>{row.display_name || row.username}</strong>
              <div className="muted">@{row.username}</div>
              <div style={{ marginTop: '0.35rem' }}>
                {row.title ? (
                  <>
                    <strong>{row.title}</strong>
                    <div className="muted">{row.artist_name}</div>
                  </>
                ) : (
                  <span className="muted">Idle</span>
                )}
              </div>
              <div className="muted tiny" style={{ marginTop: '0.25rem' }}>
                {row.playing ? 'Playing' : 'Paused'}
              </div>
            </div>
            <button
              type="button"
              className="btn secondary"
              disabled={stop.isPending}
              onClick={() => stop.mutate(row.user_id)}
            >
              Stop
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
