import React, { useEffect, useState } from 'react'

interface PositionSelectorProps {
  playerCount: number
  selectedPosition: string
  onPositionChange: (position: string) => void
  selectedAction: string
  onActionChange: (action: string) => void
}

const ACTIONS = [
  { key: 'open_raise', label: 'Open Raise' },
  { key: 'call_open', label: 'Call / Limp' },
  { key: '3bet', label: '3-Bet' },
  { key: 'fold', label: 'Fold' },
]

const PositionSelector: React.FC<PositionSelectorProps> = ({
  playerCount,
  selectedPosition,
  onPositionChange,
  selectedAction,
  onActionChange,
}) => {
  const [positions, setPositions] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch(`/api/preflop/positions?players=${playerCount}`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json() as Promise<string[]>
      })
      .then((data) => {
        setPositions(data)
        // Auto-select first position if current selection is invalid
        if (!data.includes(selectedPosition) && data.length > 0) {
          onPositionChange(data[0])
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerCount])

  return (
    <div className="panel">
      <div className="panel-title">Position</div>

      {loading && <div className="text-muted">Loading positions...</div>}
      {error && <div className="error-msg">Error: {error}</div>}

      {!loading && !error && (
        <div className="form-row">
          <label>Position</label>
          <div className="position-group">
            {positions.map((pos) => (
              <button
                key={pos}
                className={`position-btn${selectedPosition === pos ? ' selected' : ''}`}
                onClick={() => onPositionChange(pos)}
              >
                {pos}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="divider" />

      <div className="form-row">
        <label>Action to View</label>
        <div className="position-group">
          {ACTIONS.map((a) => (
            <button
              key={a.key}
              className={`position-btn${selectedAction === a.key ? ' selected' : ''}`}
              onClick={() => onActionChange(a.key)}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

export default PositionSelector
