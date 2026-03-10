import React, { useState } from 'react'
import HandGrid from './components/HandGrid'
import PositionSelector from './components/PositionSelector'
import PlayerConfig from './components/PlayerConfig'
import SolverOutput from './components/SolverOutput'

type Tab = 'preflop' | 'postflop'

interface HandFrequencies {
  open_raise: number
  call_open: number
  '3bet': number
  fold: number
}

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('preflop')

  // Shared state
  const [playerCount, setPlayerCount] = useState<number>(6)
  const [stacks, setStacks] = useState<number[]>(Array(6).fill(100))

  // Pre-flop state
  const [position, setPosition] = useState<string>('BTN')
  const [selectedAction, setSelectedAction] = useState<string>('open_raise')
  const [selectedHand, setSelectedHand] = useState<string | null>(null)
  const [handFrequencies, setHandFrequencies] = useState<HandFrequencies | null>(null)
  const [loadingFreqs, setLoadingFreqs] = useState(false)

  const handleHandSelect = (hand: string) => {
    setSelectedHand(hand)
    setHandFrequencies(null)

    // Fetch all actions for this hand
    setLoadingFreqs(true)
    const actions = ['open_raise', 'call_open', '3bet', 'fold'] as const
    Promise.all(
      actions.map((action) =>
        fetch(
          `/api/preflop/range?players=${playerCount}&position=${encodeURIComponent(position)}&action=${action}`
        )
          .then((r) => (r.ok ? (r.json() as Promise<Record<string, number>>) : {}))
          .then((data) => ({ action, freq: data[hand] ?? 0 }))
      )
    )
      .then((results) => {
        const freqs: HandFrequencies = {
          open_raise: 0,
          call_open: 0,
          '3bet': 0,
          fold: 0,
        }
        results.forEach(({ action, freq }) => {
          freqs[action] = freq
        })
        setHandFrequencies(freqs)
      })
      .catch(() => setHandFrequencies(null))
      .finally(() => setLoadingFreqs(false))
  }

  const handlePlayerCountChange = (count: number) => {
    setPlayerCount(count)
    setSelectedHand(null)
    setHandFrequencies(null)
  }

  const handlePositionChange = (pos: string) => {
    setPosition(pos)
    setSelectedHand(null)
    setHandFrequencies(null)
  }

  return (
    <div className="app-wrapper">
      <header className="app-header">
        <div>
          <h1>GTO Poker Calculator</h1>
        </div>
        <span className="subtitle">Cash Game · 100bb · No Antes</span>
      </header>

      {/* Tab bar */}
      <div className="tab-bar">
        <button
          className={`tab-btn${activeTab === 'preflop' ? ' active' : ''}`}
          onClick={() => setActiveTab('preflop')}
        >
          Pre-flop Ranges
        </button>
        <button
          className={`tab-btn${activeTab === 'postflop' ? ' active' : ''}`}
          onClick={() => setActiveTab('postflop')}
        >
          Post-flop Solver
        </button>
      </div>

      {/* Pre-flop tab */}
      {activeTab === 'preflop' && (
        <div className="preflop-layout">
          {/* Sidebar */}
          <div className="sidebar">
            <PlayerConfig
              playerCount={playerCount}
              onPlayerCountChange={handlePlayerCountChange}
              stacks={stacks}
              onStacksChange={setStacks}
              showStacks={false}
            />

            <PositionSelector
              playerCount={playerCount}
              selectedPosition={position}
              onPositionChange={handlePositionChange}
              selectedAction={selectedAction}
              onActionChange={setSelectedAction}
            />

            {/* Selected hand info panel */}
            {selectedHand && (
              <div className="panel">
                <div className="panel-title">Hand Details</div>
                <div className="selected-hand-info">
                  <div className="hand-name">{selectedHand}</div>
                  <div className="text-muted" style={{ marginBottom: 8, fontSize: '0.78rem' }}>
                    {position} · {playerCount}-handed
                  </div>

                  {loadingFreqs && (
                    <div className="text-muted">
                      <span className="loading-spinner" style={{ marginRight: 6 }} />
                      Loading...
                    </div>
                  )}

                  {handFrequencies && !loadingFreqs && (
                    <>
                      <div className="freq-row">
                        <span className="freq-label">Open Raise</span>
                        <span
                          className="freq-value"
                          style={{ color: 'var(--green)' }}
                        >
                          {(handFrequencies.open_raise * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="freq-row">
                        <span className="freq-label">3-Bet</span>
                        <span
                          className="freq-value"
                          style={{ color: 'var(--accent-gold)' }}
                        >
                          {(handFrequencies['3bet'] * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="freq-row">
                        <span className="freq-label">Call / Limp</span>
                        <span
                          className="freq-value"
                          style={{ color: '#5b8cff' }}
                        >
                          {(handFrequencies.call_open * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="freq-row">
                        <span className="freq-label">Fold</span>
                        <span
                          className="freq-value"
                          style={{ color: 'var(--red)' }}
                        >
                          {(handFrequencies.fold * 100).toFixed(1)}%
                        </span>
                      </div>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Hand Grid */}
          <HandGrid
            playerCount={playerCount}
            position={position}
            action={selectedAction}
            onHandSelect={handleHandSelect}
            selectedHand={selectedHand}
          />
        </div>
      )}

      {/* Post-flop tab */}
      {activeTab === 'postflop' && (
        <div>
          <div style={{ marginBottom: 16 }}>
            <PlayerConfig
              playerCount={playerCount}
              onPlayerCountChange={handlePlayerCountChange}
              stacks={stacks}
              onStacksChange={setStacks}
              showStacks={true}
            />
          </div>
          <SolverOutput playerCount={playerCount} stacks={stacks} />
        </div>
      )}
    </div>
  )
}

export default App
