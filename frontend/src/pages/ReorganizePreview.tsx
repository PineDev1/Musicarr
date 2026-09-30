import { useMutation } from '@tanstack/react-query'
import { api } from '../api'

/** "Preview" button + result for the dry run of Reorganize files. Changes nothing on disk. */
export function ReorganizePreview({ disabled }: { disabled?: boolean }) {
  const preview = useMutation({ mutationFn: api.reorganizePreview })
  const data = preview.data

  return (
    <>
      <button
        type="button"
        className="btn secondary"
        onClick={() => preview.mutate()}
        disabled={disabled || preview.isPending}
        title="Shows what Reorganize files would move, without moving anything"
      >
        {preview.isPending ? 'Checking…' : 'Preview reorganize'}
      </button>
      {preview.error && <p className="error">{(preview.error as Error).message}</p>}
      {data && (
        <div className="card" style={{ marginTop: '1rem', maxWidth: 900, flexBasis: '100%' }}>
          <p style={{ marginTop: 0 }}>
            <strong>{data.total_moves}</strong> file{data.total_moves === 1 ? '' : 's'} would move,{' '}
            <strong>{data.total_conflicts}</strong> blocked because the destination already exists,{' '}
            {data.already_in_place} already in place.
          </p>
          {data.total_moves === 0 && data.total_conflicts === 0 && (
            <p className="muted">Everything already matches your folder and file templates.</p>
          )}
          {data.moves.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>From</th>
                  <th>To</th>
                </tr>
              </thead>
              <tbody>
                {data.moves.map((m, i) => (
                  <tr key={i}>
                    <td style={{ wordBreak: 'break-all' }} className="muted">
                      {m.from}
                    </td>
                    <td style={{ wordBreak: 'break-all' }}>{m.to}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data.total_moves > data.moves.length && (
            <p className="muted tiny">
              Showing the first {data.moves.length} of {data.total_moves}.
            </p>
          )}
          {data.conflicts.length > 0 && (
            <>
              <h4>Would be skipped (destination exists)</h4>
              <table className="table">
                <tbody>
                  {data.conflicts.map((m, i) => (
                    <tr key={i}>
                      <td style={{ wordBreak: 'break-all' }} className="muted">
                        {m.from}
                      </td>
                      <td style={{ wordBreak: 'break-all' }}>{m.to}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </>
  )
}
