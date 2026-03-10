import React from 'react'

interface PlayerConfigProps {
  playerCount: number
  onPlayerCountChange: (count: number) => void
  stacks: number[]
  onStacksChange: (stacks: number[]) => void
  showStacks?: boolean
}

const PlayerConfig: React.FC<PlayerConfigProps> = ({
  playerCount,
  onPlayerCountChange,
  stacks,
  onStacksChange,
  showStacks = false,
}) => {
  const handlePlayerCountChange = (newCount: number) => {
    onPlayerCountChange(newCount)
    // Adjust stacks array to match new player count
    const newStacks = Array.from({ length: newCount }, (_, i) =>
      i < stacks.length ? stacks[i] : 100
    )
    onStacksChange(newStacks)
  }

  const handleStackChange = (index: number, value: string) => {
    const parsed = parseFloat(value)
    if (!isNaN(parsed) && parsed >= 0) {
      const updated = [...stacks]
      updated[index] = parsed
      onStacksChange(updated)
    }
  }

  const positionLabels: Record<number, string[]> = {
    2: ['BTN/SB', 'BB'],
    3: ['BTN', 'SB', 'BB'],
    4: ['CO', 'BTN', 'SB', 'BB'],
    5: ['HJ', 'CO', 'BTN', 'SB', 'BB'],
    6: ['UTG', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    7: ['UTG', 'UTG+1', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    8: ['UTG', 'UTG+1', 'UTG+2', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
    9: ['UTG', 'UTG+1', 'UTG+2', 'LJ', 'HJ', 'CO', 'BTN', 'SB', 'BB'],
  }

  return (
    <div className="panel">
      <div className="panel-title">Table Setup</div>

      <div className="form-row">
        <label>Number of Players: {playerCount}</label>
        <input
          type="range"
          min={2}
          max={9}
          value={playerCount}
          onChange={(e) => handlePlayerCountChange(Number(e.target.value))}
        />
        <div className="row" style={{ justifyContent: 'space-between', marginTop: 4 }}>
          <span className="text-muted">2</span>
          <span className="text-muted">9</span>
        </div>
      </div>

      <div className="form-row">
        <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
          {[2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
            <button
              key={n}
              className={`position-btn${playerCount === n ? ' selected' : ''}`}
              onClick={() => handlePlayerCountChange(n)}
            >
              {n}
            </button>
          ))}
        </div>
      </div>

      {showStacks && (
        <>
          <div className="divider" />
          <div className="panel-title" style={{ fontSize: '0.85rem' }}>
            Stack Sizes (bb)
          </div>
          <div className="stacks-grid">
            {Array.from({ length: playerCount }, (_, i) => (
              <div key={i} className="stack-input-group">
                <label>{positionLabels[playerCount]?.[i] ?? `P${i + 1}`}</label>
                <input
                  type="number"
                  min={0}
                  max={999}
                  step={0.5}
                  value={stacks[i] ?? 100}
                  onChange={(e) => handleStackChange(i, e.target.value)}
                />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export default PlayerConfig
