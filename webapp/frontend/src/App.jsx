import { useEffect } from 'react'
import Board          from './components/Board.jsx'
import EvalBar        from './components/EvalBar.jsx'
import MoveList       from './components/MoveList.jsx'
import Commentary     from './components/Commentary.jsx'
import AnalysisInput  from './components/AnalysisInput.jsx'
import ProgressBars   from './components/ProgressBars.jsx'
import Navigation     from './components/Navigation.jsx'
import ConfigPanel    from './components/ConfigPanel.jsx'
import { useAnalysis } from './hooks/useAnalysis.js'
import { ARROW_PLAYED, ARROW_BEST } from './constants.js'

const BOARD_SIZE = 520

export default function App() {
  const {
    pgnInput, setPgnInput,
    ourSide,  setOurSide,
    configPreset, setConfigPreset,
    configFlags,  setConfigFlags,
    thinking,     setThinking,
    analyze,
    positions, currentIdx, setCurrentIdx,
    analyzing, error,
    total, engineProgress, commentaryProgress, phase,
  } = useAnalysis()

  const current = positions[currentIdx] ?? null

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === 'TEXTAREA') return
      if (e.key === 'ArrowLeft')  setCurrentIdx(i => Math.max(0, i - 1))
      if (e.key === 'ArrowRight') setCurrentIdx(i => Math.min(positions.length - 1, i + 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [positions.length, setCurrentIdx])

  const arrows = []
  if (current?.uci) {
    arrows.push([current.uci.slice(0, 2), current.uci.slice(2, 4), ARROW_PLAYED])
  }
  if (current?.best_move_uci && current.best_move_uci !== current.uci) {
    arrows.push([current.best_move_uci.slice(0, 2), current.best_move_uci.slice(2, 4), ARROW_BEST])
  }

  const nav = {
    prev:    () => setCurrentIdx(i => Math.max(0, i - 1)),
    next:    () => setCurrentIdx(i => Math.min(positions.length - 1, i + 1)),
    toStart: () => setCurrentIdx(0),
    toEnd:   () => setCurrentIdx(positions.length - 1),
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>♟ Chess Analyzer</h1>
        <span className="subtitle">ShashChess · AI Commentary</span>
      </header>

      <AnalysisInput
        pgnInput={pgnInput}
        onPgnChange={setPgnInput}
        ourSide={ourSide}
        onSideToggle={() => setOurSide(s => s === 'white' ? 'black' : 'white')}
        onAnalyze={analyze}
        analyzing={analyzing}
      />

      <ConfigPanel
        configPreset={configPreset}
        setConfigPreset={setConfigPreset}
        configFlags={configFlags}
        setConfigFlags={setConfigFlags}
        thinking={thinking}
        setThinking={setThinking}
        disabled={analyzing}
      />

      {error && <div className="error-msg">⚠ {error}</div>}

      <ProgressBars
        phase={phase}
        engineProgress={engineProgress}
        commentaryProgress={commentaryProgress}
        total={total}
      />

      {positions.length > 0 && current && (
        <div className="main-layout">
          <div className="board-section">
            <div className="board-with-eval">
              <EvalBar evalCp={current.eval_cp} evalMate={current.eval_mate} height={BOARD_SIZE} />
              <Board fen={current.fen} arrows={arrows} boardWidth={BOARD_SIZE} />
            </div>

            <Navigation currentIdx={currentIdx} total={positions.length} nav={nav} />

            <div className="legend">
              <div className="legend-item">
                <div className="legend-arrow played" /><span>Played move</span>
              </div>
              <div className="legend-item">
                <div className="legend-arrow best" /><span>Engine best</span>
              </div>
            </div>
          </div>

          <div className="analysis-section">
            <MoveList positions={positions} currentIdx={currentIdx} onSelect={setCurrentIdx} />
            <Commentary position={current} />
          </div>
        </div>
      )}
    </div>
  )
}
