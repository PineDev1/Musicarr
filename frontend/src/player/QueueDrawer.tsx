import { useRef, useState, type DragEvent } from 'react'
import { IconClose, IconGrip } from './icons'
import { formatTime, usePlayerQueue } from './PlayerQueueContext'

type Props = {
  onClose: () => void
}

export function QueueDrawer({ onClose }: Props) {
  const q = usePlayerQueue()
  const [dragFrom, setDragFrom] = useState<number | null>(null)
  const [dragOver, setDragOver] = useState<number | null>(null)
  const draggedRef = useRef(false)

  function onDragStart(e: DragEvent, index: number) {
    setDragFrom(index)
    draggedRef.current = false
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(index))
    // Improve drag image on some browsers
    if (e.currentTarget instanceof HTMLElement) {
      e.dataTransfer.setDragImage(e.currentTarget, 24, 24)
    }
  }

  function onDragOver(e: DragEvent, index: number) {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (dragOver !== index) setDragOver(index)
  }

  function onDrop(e: DragEvent, to: number) {
    e.preventDefault()
    const from = dragFrom ?? Number(e.dataTransfer.getData('text/plain'))
    if (Number.isFinite(from) && from !== to) {
      q.reorder(from, to)
      draggedRef.current = true
    }
    setDragFrom(null)
    setDragOver(null)
  }

  function onDragEnd() {
    setDragFrom(null)
    setDragOver(null)
  }

  return (
    <div className="queue-drawer">
      <div className="queue-head">
        <div>
          <strong>Queue</strong>
          <div className="muted tiny">{q.tracks.length} tracks — drag to reorder</div>
        </div>
        <div className="queue-head-actions">
          {q.tracks.length > 0 && (
            <button type="button" className="btn ghost" onClick={() => q.clearQueue()}>
              Clear
            </button>
          )}
          <button type="button" className="pill-icon-btn" aria-label="Close queue" onClick={onClose}>
            <IconClose size={18} />
          </button>
        </div>
      </div>

      {!q.tracks.length && <p className="muted queue-empty">Queue is empty — play something.</p>}

      <ul className="queue-list">
        {q.tracks.map((t, i) => {
          const isCurrent = i === q.index
          const isDragging = dragFrom === i
          const isOver = dragOver === i && dragFrom !== null && dragFrom !== i
          return (
            <li
              key={`${t.id}-${i}`}
              className={[
                isCurrent ? 'active' : '',
                isDragging ? 'dragging' : '',
                isOver ? 'drop-target' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              draggable
              onDragStart={(e) => onDragStart(e, i)}
              onDragOver={(e) => onDragOver(e, i)}
              onDrop={(e) => onDrop(e, i)}
              onDragEnd={onDragEnd}
              onDragLeave={() => {
                if (dragOver === i) setDragOver(null)
              }}
            >
              <span className="queue-grip" title="Drag to reorder" aria-hidden>
                <IconGrip size={16} />
              </span>
              <button
                type="button"
                className="queue-row"
                onClick={() => {
                  if (draggedRef.current) {
                    draggedRef.current = false
                    return
                  }
                  q.jumpTo(i)
                }}
              >
                {t.cover_url ? <img src={t.cover_url} alt="" /> : <div className="q-art" />}
                <span className="queue-meta">
                  <span className="queue-title">
                    {isCurrent && <span className="queue-now">Now</span>}
                    {t.title}
                  </span>
                  <span className="muted tiny">
                    {t.artist_name}
                    {t.duration ? ` · ${formatTime(t.duration)}` : ''}
                  </span>
                </span>
              </button>
              <button
                type="button"
                className="pill-icon-btn"
                aria-label="Remove from queue"
                onClick={() => q.removeAt(i)}
              >
                <IconClose size={16} />
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
