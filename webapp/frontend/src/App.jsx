import { useState, useCallback, useEffect, useRef } from 'react'
import Board from './components/Board.jsx'
import EvalBar from './components/EvalBar.jsx'
import MoveList from './components/MoveList.jsx'
import Commentary from './components/Commentary.jsx'

export const QUALITY_SYMBOLS = {
  blunder: '??',
  mistake: '?',
  inaccuracy: '?!',
  good: '',
  excellent: '!',
  best: '✓',
  book: '',
}

export default function App() {
  const [pgnInput, setPgnInput] = useState('')
  const [positions, setPositions] = useState([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState(null)
  const [total, setTotal] = useState(0)
  const [engineProgress, setEngineProgress] = useState(0)
  const [commentaryProgress, setCommentaryProgress] = useState(0)
  const [phase, setPhase] = useState('idle') // idle | engine | commentary | done

  const readerRef = useRef(null)

  const current = positions[currentIdx] ?? null

  const handleMessage = useCallback((data) => {
    switch (data.type) {
      case 'start':
        setTotal(data.total)
        setPhase('engine')
        break
      case 'engine':
        setPositions(prev => {
          const next = [...prev]
          while (next.length <= data.index) next.push(null)
          next[data.index] = data.position
          return next
        })
        setEngineProgress(data.index + 1)
        break
      case 'commentary_start':
        setPhase('commentary')
        setCommentaryProgress(0)
        break
      case 'commentary':
        setPositions(prev => {
          const next = [...prev]
          if (next[data.index]) {
            next[data.index] = { ...next[data.index], commentary: data.commentary }
          }
          return next
        })
        setCommentaryProgress(p => p + 1)
        break
      case 'complete':
        setPhase('done')
        setAnalyzing(false)
        break
      case 'error':
        setError(data.message)
        setAnalyzing(false)
        setPhase('idle')
        break
    }
  }, [])

  const analyze = useCallback(async () => {
    if (!pgnInput.trim()) return

    setAnalyzing(true)
    setError(null)
    setPositions([])
    setCurrentIdx(0)
    setTotal(0)
    setEngineProgress(0)
    setCommentaryProgress(0)
    setPhase('idle')

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pgn: pgnInput }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader = response.body.getReader()
      readerRef.current = reader
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() ?? ''

        for (const chunk of chunks) {
          const line = chunk.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          try { handleMessage(JSON.parse(line.slice(6))) } catch {}
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      setAnalyzing(false)
    }
  }, [pgnInput, handleMessage])

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'TEXTAREA') return
      if (e.key === 'ArrowLeft')  setCurrentIdx(i => Math.max(0, i - 1))
      if (e.key === 'ArrowRight') setCurrentIdx(i => Math.min(positions.length - 1, i + 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [positions.length])

  const prev = () => setCurrentIdx(i => Math.max(0, i - 1))
  const next = () => setCurrentIdx(i => Math.min(positions.length - 1, i + 1))
  const toStart = () => setCurrentIdx(0)
  const toEnd = () => setCurrentIdx(positions.length - 1)

  // Build arrows: blue = played move, green = engine best (if different)
  const arrows = []
  if (current?.uci) {
    arrows.push([current.uci.slice(0, 2), current.uci.slice(2, 4), 'rgba(30,120,230,0.75)'])
  }
  if (current?.best_move_uci && current.best_move_uci !== current.uci) {
    arrows.push([current.best_move_uci.slice(0, 2), current.best_move_uci.slice(2, 4), 'rgba(0,190,80,0.85)'])
  }

  const BOARD_SIZE = 520

  return (
    <div className="app">
      <header className="app-header">
        <h1>♟ Chess Analyzer</h1>
        <span className="subtitle">ShashChess · AI Commentary</span>
      </header>

      <div className="input-section">
        <textarea
          className="pgn-input"
          value={pgnInput}
          onChange={e => setPgnInput(e.target.value)}
          placeholder="Paste PGN or FEN here…"
          rows={4}
          disabled={analyzing}
        />
        <button
          className="analyze-btn"
          onClick={analyze}
          disabled={analyzing || !pgnInput.trim()}
        >
          {analyzing ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>

      {error && <div className="error-msg">⚠ {error}</div>}

      {phase !== 'idle' && phase !== 'done' && (
        <div className="progress-section">
          <div className="progress-item">
            <span>Engine: {engineProgress}/{total}</span>
            <div className="progress-bar">
              <div
                className="progress-fill engine"
                style={{ width: `${total ? (engineProgress / total) * 100 : 0}%` }}
              />
            </div>
          </div>
          {phase === 'commentary' && (
            <div className="progress-item">
              <span>Commentary: {commentaryProgress}/{total}</span>
              <div className="progress-bar">
                <div
                  className="progress-fill commentary"
                  style={{ width: `${total ? (commentaryProgress / total) * 100 : 0}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {positions.length > 0 && current && (
        <div className="main-layout">
          <div className="board-section">
            <div className="board-with-eval">
              <EvalBar
                evalCp={current.eval_cp}
                evalMate={current.eval_mate}
                height={BOARD_SIZE}
              />
              <Board
                fen={current.fen}
                arrows={arrows}
                boardWidth={BOARD_SIZE}
              />
            </div>

            {positions.length > 1 ? (
              <div className="nav-controls">
                <button className="nav-btn" onClick={toStart} disabled={currentIdx === 0}>⏮</button>
                <button className="nav-btn" onClick={prev}    disabled={currentIdx === 0}>◀</button>
                <span className="move-counter">
                  {currentIdx === 0
                    ? `Start / ${positions.length - 1} moves`
                    : `Move ${currentIdx} / ${positions.length - 1}`}
                </span>
                <button className="nav-btn" onClick={next}   disabled={currentIdx >= positions.length - 1}>▶</button>
                <button className="nav-btn" onClick={toEnd}  disabled={currentIdx >= positions.length - 1}>⏭</button>
              </div>
            ) : (
              <div className="nav-controls">
                <span className="move-counter" style={{ color: 'var(--text-dim)' }}>
                  Single position — paste PGN to navigate moves
                </span>
              </div>
            )}

            <div className="legend">
              <div className="legend-item">
                <div className="legend-arrow played" />
                <span>Played move</span>
              </div>
              <div className="legend-item">
                <div className="legend-arrow best" />
                <span>Engine best</span>
              </div>
            </div>
          </div>

          <div className="analysis-section">
            <MoveList
              positions={positions}
              currentIdx={currentIdx}
              onSelect={setCurrentIdx}
            />
            <Commentary position={current} />
          </div>
        </div>
      )}
    </div>
  )
}
