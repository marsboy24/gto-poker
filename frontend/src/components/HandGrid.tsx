import React, { useEffect, useState, useCallback } from 'react'

interface HandGridProps {
  playerCount: number
  position: string
  action: string
  onHandSelect: (hand: string) => void
  selectedHand: string | null
}

type RangeData = Record<string, number>

// The 13 ranks in order (high to low)
const RANKS = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']

/**
 * Compute the canonical hand string for a cell in the 13x13 grid.
 * row = rank index for rows (A=0, 2=12)
 * col = rank index for cols
 * Upper-right triangle (col > row): suited
 * Diagonal (col == row): pair
 * Lower-left triangle (col < row): offsuit
 */
function cellHand(row: number, col: number): string {
  const r1 = RANKS[row]
  const r2 = RANKS[col]

  if (row === col) {
    return r1 + r2  // pair
  } else if (col > row) {
    // Upper-right triangle: r1 is the higher rank (smaller index), suited
    return r1 + r2 + 's'
  } else {
    // Lower-left triangle: r2 has a smaller index = higher rank, offsuit
    return r2 + r1 + 'o'
  }
}

function freqToClass(freq: number | undefined): string {
  if (freq === undefined || freq === 0) return 'grey'
  if (freq >= 0.66) return 'raise'
  if (freq >= 0.25) return 'mixed'
  return 'fold'
}

function freqToColor(freq: number | undefined): string {
  if (freq === undefined || freq === 0) return ''
  // Interpolate a background to show exact frequency within category
  if (freq >= 0.66) {
    const intensity = Math.min(1, freq)
    return `rgba(60, 185, 110, ${0.5 + intensity * 0.5})`
  }
  if (freq >= 0.25) {
    return `rgba(212, 168, 67, ${0.5 + freq * 0.5})`
  }
  return `rgba(224, 92, 92, ${0.3 + freq * 1.5})`
}

const HandGrid: React.FC<HandGridProps> = ({
  playerCount,
  position,
  action,
  onHandSelect,
  selectedHand,
}) => {
  const [rangeData, setRangeData] = useState<RangeData>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [hoveredHand, setHoveredHand] = useState<string | null>(null)
  const [hoveredCell, setHoveredCell] = useState<{ row: number; col: number } | null>(null)

  const fetchRange = useCallback(() => {
    if (!position) return
    setLoading(true)
    setError(null)

    const url = `/api/preflop/range?players=${playerCount}&position=${encodeURIComponent(position)}&action=${encodeURIComponent(action)}`
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`)
        return res.json() as Promise<RangeData>
      })
      .then((data) => {
        setRangeData(data)
      })
      .catch((err: Error) => {
        setError(err.message)
        setRangeData({})
      })
      .finally(() => setLoading(false))
  }, [playerCount, position, action])

  useEffect(() => {
    fetchRange()
  }, [fetchRange])

  const cells = RANKS.flatMap((_, row) =>
    RANKS.map((_, col) => ({ row, col, hand: cellHand(row, col) }))
  )

  return (
    <div className="panel">
      <div className="panel-title">
        Hand Range Grid — {position} ({action.replace('_', ' ')})
      </div>

      {loading && (
        <div className="text-muted" style={{ marginBottom: 12 }}>
          <span className="loading-spinner" style={{ marginRight: 8 }} />
          Loading ranges...
        </div>
      )}
      {error && (
        <div className="error-msg" style={{ marginBottom: 12 }}>
          Failed to load range: {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {/* Column headers */}
          <div className="hand-grid-wrapper">
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '18px repeat(13, 1fr)',
                gap: '2px',
                minWidth: 520,
                marginBottom: 2,
              }}
            >
              <div /> {/* corner */}
              {RANKS.map((r) => (
                <div
                  key={r}
                  style={{
                    textAlign: 'center',
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    color: 'var(--text-muted)',
                    paddingBottom: 2,
                  }}
                >
                  {r}
                </div>
              ))}
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '18px repeat(13, 1fr)',
                gap: '2px',
                minWidth: 520,
              }}
            >
              {RANKS.flatMap((rank, row) => [
                // Row label
                <div
                  key={`label-${row}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    color: 'var(--text-muted)',
                  }}
                >
                  {rank}
                </div>,
                // Row cells
                ...RANKS.map((_, col) => {
                  const hand = cellHand(row, col)
                  const freq = rangeData[hand]
                  const cls = freqToClass(freq)
                  const color = freqToColor(freq)
                  const isSelected = selectedHand === hand
                  const isHovered = hoveredHand === hand

                  return (
                    <div
                      key={`${row}-${col}`}
                      className={`hand-cell ${cls}${isSelected ? ' selected-hand' : ''}`}
                      style={color ? { background: color } : {}}
                      onClick={() => onHandSelect(hand)}
                      onMouseEnter={() => {
                        setHoveredHand(hand)
                        setHoveredCell({ row, col })
                      }}
                      onMouseLeave={() => {
                        setHoveredHand(null)
                        setHoveredCell(null)
                      }}
                    >
                      {hand}
                      {isHovered && hoveredCell?.row === row && hoveredCell?.col === col && (
                        <div className="hand-cell-tooltip">
                          <strong>{hand}</strong>
                          {' — '}
                          {freq !== undefined ? `${(freq * 100).toFixed(1)}%` : 'Not in range'}
                        </div>
                      )}
                    </div>
                  )
                }),
              ])}
            </div>
          </div>

          {/* Legend */}
          <div className="grid-legend">
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: 'var(--green)' }} />
              Raise ≥ 66%
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: 'var(--yellow)' }} />
              Mixed 25–66%
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: 'var(--red)' }} />
              Rare &lt; 25%
            </div>
            <div className="legend-item">
              <div className="legend-swatch" style={{ background: 'var(--grey)' }} />
              Not in range
            </div>
            <div className="legend-item" style={{ marginLeft: 'auto', fontStyle: 'italic' }}>
              Upper-right = suited · Diagonal = pairs · Lower-left = offsuit
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default HandGrid
