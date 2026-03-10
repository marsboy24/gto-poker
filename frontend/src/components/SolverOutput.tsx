import React, { useState, useRef, useCallback } from 'react'

interface SolverRequest {
  board: string[]
  hero_hand: string[]
  players: number
  pot: number
  stacks: number[]
  hero_position: number
  betting_history: Record<string, unknown>[]
}

interface SolverResult {
  strategy: Record<string, number>
  equity: number
  iterations: number
}

interface SolverOutputProps {
  playerCount: number
  stacks: number[]
}

const ACTION_COLORS: Record<string, string> = {
  fold: 'action-fold',
  check: 'action-check',
  call: 'action-call',
  bet: 'action-bet',
  raise: 'action-raise',
}

function getActionColor(actionKey: string): string {
  const base = actionKey.split('_')[0]
  return ACTION_COLORS[base] ?? 'action-other'
}

function formatActionLabel(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/Bb/g, 'bb')
}

// Maps action base key to a CSS variable for the label text color
function getActionLabelColor(actionKey: string): string {
  const base = actionKey.split('_')[0]
  const map: Record<string, string> = {
    fold:  'var(--action-fold)',
    check: 'var(--action-check)',
    call:  'var(--action-call)',
    bet:   'var(--action-bet)',
    raise: 'var(--action-raise)',
  }
  return map[base] ?? 'var(--text-secondary)'
}

const TOTAL_ITERATIONS = 1000

const SolverOutput: React.FC<SolverOutputProps> = ({ playerCount, stacks }) => {
  const [boardCards, setBoardCards] = useState<string[]>(['', '', '', '', ''])
  const [heroHand, setHeroHand] = useState<string[]>(['', ''])
  const [pot, setPot] = useState<number>(10)
  const [heroPosition, setHeroPosition] = useState<number>(0)
  const [useWebSocket, setUseWebSocket] = useState<boolean>(true)

  const [result, setResult] = useState<SolverResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)

  const getBoard = useCallback((): string[] => {
    return boardCards.filter((c) => c.trim().length === 2)
  }, [boardCards])

  const getHeroHand = useCallback((): string[] => {
    return heroHand.filter((c) => c.trim().length === 2)
  }, [heroHand])

  const buildRequest = useCallback((): SolverRequest | null => {
    const board = getBoard()
    const hand = getHeroHand()

    if (board.length < 3) {
      setError('Please enter at least 3 board cards (flop).')
      return null
    }
    if (hand.length !== 2) {
      setError('Please enter exactly 2 hero hole cards.')
      return null
    }

    return {
      board,
      hero_hand: hand,
      players: playerCount,
      pot,
      stacks: stacks.slice(0, playerCount),
      hero_position: heroPosition,
      betting_history: [],
    }
  }, [getBoard, getHeroHand, playerCount, pot, stacks, heroPosition])

  const solveWithRest = useCallback(async () => {
    const req = buildRequest()
    if (!req) return

    setLoading(true)
    setError(null)
    setResult(null)
    setProgress(50)

    try {
      const res = await fetch('/api/postflop/solve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(req),
      })
      if (!res.ok) {
        const text = await res.text()
        throw new Error(`HTTP ${res.status}: ${text}`)
      }
      const data = (await res.json()) as SolverResult
      setResult(data)
      setProgress(100)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [buildRequest])

  const solveWithWebSocket = useCallback(() => {
    const req = buildRequest()
    if (!req) return

    if (wsRef.current) {
      wsRef.current.close()
    }

    setLoading(true)
    setError(null)
    setResult(null)
    setProgress(0)

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/postflop/solve`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify(req))
    }

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as {
          iteration?: number
          strategy?: Record<string, number>
          equity?: number
          error?: string
        }

        if (data.error) {
          setError(data.error)
          setLoading(false)
          ws.close()
          return
        }

        const iter = data.iteration ?? 0
        setProgress(Math.round((iter / TOTAL_ITERATIONS) * 100))

        if (data.strategy && data.equity !== undefined) {
          setResult({
            strategy: data.strategy,
            equity: data.equity,
            iterations: iter,
          })
        }

        if (iter >= TOTAL_ITERATIONS) {
          setLoading(false)
        }
      } catch {
        // ignore parse errors
      }
    }

    ws.onerror = () => {
      setError('WebSocket connection failed. Falling back to REST.')
      setLoading(false)
      ws.close()
    }

    ws.onclose = () => {
      setLoading(false)
    }
  }, [buildRequest])

  const handleSolve = () => {
    if (useWebSocket) {
      solveWithWebSocket()
    } else {
      void solveWithRest()
    }
  }

  const handleStop = () => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setLoading(false)
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
    <div className="postflop-layout">
      {/* ── Left: Input panels — baize surface (slightly lighter) ── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>

        {/* Board input — inset card entry */}
        <div className="panel">
          <div className="panel-title">Board Cards</div>
          <div
            className="text-muted"
            style={{ marginBottom: 'var(--space-1)', fontFamily: 'var(--font-mono)' }}
          >
            Enter 3–5 cards (e.g. As Kh 2c)
          </div>
          <div className="board-input">
            {boardCards.map((card, i) => (
              <input
                key={i}
                type="text"
                maxLength={2}
                placeholder={i < 3 ? `C${i + 1}` : i === 3 ? 'Tn' : 'Rv'}
                value={card}
                onChange={(e) => {
                  const updated = [...boardCards]
                  updated[i] = e.target.value
                  setBoardCards(updated)
                }}
                style={{ textTransform: 'uppercase' }}
              />
            ))}
          </div>
        </div>

        {/* Hero hand — inset card entry */}
        <div className="panel">
          <div className="panel-title">Hero Hand</div>
          <div className="hand-input">
            {heroHand.map((card, i) => (
              <input
                key={i}
                type="text"
                maxLength={2}
                placeholder={i === 0 ? 'C1' : 'C2'}
                value={card}
                onChange={(e) => {
                  const updated = [...heroHand]
                  updated[i] = e.target.value
                  setHeroHand(updated)
                }}
                style={{ textTransform: 'uppercase' }}
              />
            ))}
          </div>
        </div>

        {/* Game parameters */}
        <div className="panel">
          <div className="panel-title">Game Parameters</div>

          <div className="form-row">
            <label>Pot Size (bb)</label>
            <input
              type="number"
              min={0.5}
              max={9999}
              step={0.5}
              value={pot}
              onChange={(e) => setPot(parseFloat(e.target.value) || 0)}
              style={{ fontFamily: 'var(--font-mono)', fontVariantNumeric: 'tabular-nums' }}
            />
          </div>

          <div className="form-row">
            <label>Hero Position</label>
            <select
              value={heroPosition}
              onChange={(e) => setHeroPosition(Number(e.target.value))}
            >
              {(positionLabels[playerCount] ?? []).map((pos, i) => (
                <option key={i} value={i}>
                  {pos} (seat {i})
                </option>
              ))}
            </select>
          </div>

          <div className="form-row">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, textTransform: 'none', letterSpacing: 0 }}>
              <input
                type="checkbox"
                checked={useWebSocket}
                onChange={(e) => setUseWebSocket(e.target.checked)}
                style={{ width: 'auto' }}
              />
              <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontFamily: 'var(--font-ui)' }}>
                Stream via WebSocket
              </span>
            </label>
          </div>

          {error && <div className="error-msg">{error}</div>}

          <div className="row" style={{ gap: 'var(--space-1)', marginTop: 'var(--space-2)' }}>
            <button
              className="btn btn-primary"
              onClick={handleSolve}
              disabled={loading}
              style={{ flex: 1 }}
            >
              {loading ? (
                <>
                  <span className="loading-spinner" />
                  Solving...
                </>
              ) : (
                'Solve'
              )}
            </button>
            {loading && (
              <button className="btn btn-secondary" onClick={handleStop}>
                Stop
              </button>
            )}
          </div>

          {loading && (
            <div className="progress-wrap">
              <div className="progress-label">
                {progress < 100 ? `MCCFR ${progress}%` : 'Complete'}
              </div>
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Right: Output panel — felt base surface (slightly darker) ── */}
      <div
        className="panel"
        style={{
          background: 'var(--felt)',
          borderColor: 'var(--border-strong)',
        }}
      >
        <div className="panel-title panel-title-gold">Solver Results</div>

        {!result && !loading && (
          <div
            className="text-muted"
            style={{
              padding: 'var(--space-4) 0',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              lineHeight: 1.7,
            }}
          >
            Enter board + hole cards, then click Solve.<br />
            GTO strategy computed via MCCFR.
          </div>
        )}

        {loading && !result && (
          <div
            className="text-muted"
            style={{
              padding: 'var(--space-4) 0',
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
            }}
          >
            <span className="loading-spinner" />
            Running MCCFR solver...
          </div>
        )}

        {result && (
          <>
            {/* Equity display — monospace tabular-nums */}
            <div className="equity-badge">
              <span className="eq-label">Hero Equity</span>
              <span className="equity-number">
                {(result.equity * 100).toFixed(1)}%
              </span>
            </div>

            <div className="divider" />

            {/* Strategy section header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'baseline',
                justifyContent: 'space-between',
                marginBottom: 'var(--space-2)',
              }}
            >
              <div
                className="panel-title"
                style={{ marginBottom: 0, borderBottom: 'none', paddingBottom: 0 }}
              >
                GTO Strategy
              </div>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-muted)',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {result.iterations.toLocaleString()} iter
              </span>
            </div>

            <div className="strategy-chart">
              {Object.entries(result.strategy)
                .sort(([, a], [, b]) => b - a)
                .map(([action, freq]) => {
                  const colorClass = getActionColor(action)
                  const labelColor = getActionLabelColor(action)
                  const pct = (freq * 100).toFixed(1)
                  return (
                    <div key={action} className="strategy-bar-row">
                      <div
                        className="strategy-bar-label"
                        title={action}
                        style={{ color: labelColor }}
                      >
                        {formatActionLabel(action)}
                      </div>
                      <div className="strategy-bar-track">
                        <div
                          className={`strategy-bar-fill ${colorClass}`}
                          style={{ width: `${freq * 100}%` }}
                        />
                      </div>
                      <div className="strategy-bar-pct">{pct}%</div>
                    </div>
                  )
                })}
            </div>

            {loading && (
              <div className="progress-wrap" style={{ marginTop: 'var(--space-3)' }}>
                <div className="progress-label">Refining... {progress}%</div>
                <div className="progress-track">
                  <div className="progress-fill" style={{ width: `${progress}%` }} />
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default SolverOutput
