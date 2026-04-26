import { useState, useCallback, useEffect, useRef } from 'react'
import { Chess } from 'chess.js'
import type { MLCEngine } from '@mlc-ai/web-llm'
import Board, { type Arrow } from './components/Board'
import EvalBar from './components/EvalBar'
import MoveList from './components/MoveList'
import Commentary from './components/Commentary'
import LoadProgress from './components/LoadProgress'

import { useEngine } from './engine/useEngine'
import { loadLLM, askLLM } from './llm/webllm'
import { buildPrompt, buildPromptSections } from './agent/prompt'
import type { Position, MoveQuality } from './types'
import './App.css'

const BOARD_SIZE = 520

function getMoveQuality(lossCp: number | null): MoveQuality {
  if (lossCp === null || lossCp <= 5) return 'best'
  if (lossCp < 20) return 'excellent'
  if (lossCp < 50) return 'good'
  if (lossCp < 100) return 'inaccuracy'
  if (lossCp < 200) return 'mistake'
  return 'blunder'
}

function autoQuestion(lossCp: number | null): string {
  if (lossCp === null || lossCp < 50) return 'plan'
  if (lossCp > 200) return 'best_move'
  return 'explain'
}

// Parse PGN or FEN into Position array (index 0 = start)
function parsePgn(input: string): Position[] | null {
  const trimmed = input.trim()
  try {
    const chess = new Chess()
    const positions: Position[] = []

    // FEN detection: contains rank separator '/' and side-to-move
    if (trimmed.includes('/') && /\s[wb]\s/.test(trimmed)) {
      chess.load(trimmed)
      positions.push({
        fen: chess.fen(), san: null, uci: null, color: null, moveNumber: null,
        evalCp: null, evalMate: null, evalLossCp: null,
        bestMoveSan: null, bestMoveUci: null, pvSan: [],
        quality: null, shashinType: null, commentary: null, movesHistory: [],
      })
      return positions
    }

    chess.loadPgn(trimmed)
    const history = chess.history({ verbose: true })
    const replay = new Chess()

    positions.push({
      fen: replay.fen(), san: null, uci: null, color: null, moveNumber: null,
      evalCp: null, evalMate: null, evalLossCp: null,
      bestMoveSan: null, bestMoveUci: null, pvSan: [],
      quality: null, shashinType: null, commentary: null, movesHistory: [],
    })

    let movesHistory: string[] = []
    for (const mv of history) {
      movesHistory = [...movesHistory, mv.san]
      replay.move(mv.san)
      const isWhite = mv.color === 'w'
      const moveNum = isWhite
        ? Math.ceil(positions.length / 2)
        : Math.ceil((positions.length - 1) / 2)
      positions.push({
        fen: replay.fen(),
        san: mv.san,
        uci: mv.from + mv.to + (mv.promotion ?? ''),
        color: isWhite ? 'white' : 'black',
        moveNumber: moveNum,
        evalCp: null, evalMate: null, evalLossCp: null,
        bestMoveSan: null, bestMoveUci: null, pvSan: [],
        quality: null, shashinType: null, commentary: null,
        movesHistory: [...movesHistory],
      })
    }
    return positions
  } catch {
    return null
  }
}

export default function App() {
  const [pgnInput, setPgnInput] = useState('')
  const [positions, setPositions] = useState<(Position | null)[]>([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [engineProgress, setEngineProgress] = useState(0)
  const [commentaryProgress, setCommentaryProgress] = useState(0)
  const [phase, setPhase] = useState<'idle' | 'engine' | 'commentary' | 'done'>('idle')

  const [llmEngine, setLlmEngine] = useState<MLCEngine | null>(null)
  const [llmLoading, setLlmLoading] = useState(false)
  const [llmProgress, setLlmProgress] = useState(0)
  const [llmProgressText, setLlmProgressText] = useState('')

  const abortRef = useRef<AbortController | null>(null)
  const analyzedPositionsRef = useRef<(Position | null)[]>([])
  const { analyze, engineState, engineError, engineLog, debugLines } = useEngine()

  const current = positions[currentIdx] ?? null

  // Preload LLM on mount
  useEffect(() => {
    setLlmLoading(true)
    loadLLM(({ progress, text }) => {
      setLlmProgress(progress)
      setLlmProgressText(text)
    })
      .then((eng) => { setLlmEngine(eng); setLlmLoading(false) })
      .catch((e) => { console.warn('WebLLM load failed:', e); setLlmLoading(false) })
  }, [])

  const handleAnalyze = useCallback(async () => {
    if (!pgnInput.trim()) return
    if (engineState === 'unavailable') {
      setError('ShashChess engine not loaded — build the WASM engine first (see scripts/build-wasm.sh).')
      return
    }
    if (engineState === 'loading') {
      setError('Engine is still loading, please wait…')
      return
    }

    const parsed = parsePgn(pgnInput)
    if (!parsed) { setError('Invalid PGN or FEN input.'); return }

    abortRef.current?.abort()
    const abort = new AbortController()
    abortRef.current = abort

    setAnalyzing(true)
    setError(null)
    setPositions(parsed)
    analyzedPositionsRef.current = [...parsed]
    setCurrentIdx(0)
    setEngineProgress(0)
    setCommentaryProgress(0)
    setPhase('engine')

    const total = parsed.length
    let prevEvalCpWhite: number | null = null

    // ── Phase 1: engine analysis ──────────────────────────────────────
    for (let i = 0; i < total; i++) {
      if (abort.signal.aborted) break
      const pos = parsed[i]
      if (!pos) continue

      try {
        const result = await analyze(pos.fen, 15)

        // Eval loss = how much worse White's eval got after this move
        const lossCp =
          i > 0 && prevEvalCpWhite !== null && result.scoreCp !== null
            ? Math.max(0, prevEvalCpWhite - result.scoreCp)
            : null

        const updated: Position = {
          ...pos,
          evalCp: result.scoreCp,
          evalMate: result.mateIn,
          evalLossCp: lossCp,
          bestMoveSan: result.bestMoveSan,
          bestMoveUci: result.bestMoveUci,
          pvSan: result.pvSan,
          quality: i === 0 ? null : getMoveQuality(lossCp),
          shashinType: result.shashinType,
          rawEngineLines: result.rawLines,
        }

        prevEvalCpWhite = result.scoreCp
        analyzedPositionsRef.current[i] = updated
        setPositions((prev) => { const n = [...prev]; n[i] = updated; return n })
        setEngineProgress(i + 1)
      } catch (e) {
        console.warn(`Engine failed for position ${i}:`, e)
        setEngineProgress(i + 1)
      }
    }

    if (abort.signal.aborted) { setAnalyzing(false); return }

    // ── Phase 2: LLM commentary ───────────────────────────────────────
    setPhase('commentary')
    if (llmEngine) {
      for (let i = 0; i < total; i++) {
        if (abort.signal.aborted) break
        const pos = analyzedPositionsRef.current[i]
        if (!pos || pos.shashinType === null) { setCommentaryProgress(i + 1); continue }

        const promptParams = {
          fen: pos.fen,
          scoreCp: pos.evalCp,
          mateIn: pos.evalMate,
          wdlWin: 500, wdlDraw: 0, wdlLoss: 500,
          bestMoveSan: pos.bestMoveSan,
          shashinType: pos.shashinType,
          sideToMove: pos.color ?? 'white',
          movesHistory: pos.movesHistory,
          playedMove: pos.san,
          level: 'intermediate',
          question: autoQuestion(pos.evalLossCp),
        }
        const prompt = buildPrompt(promptParams)
        const promptSections = buildPromptSections(promptParams)
        analyzedPositionsRef.current[i] = { ...analyzedPositionsRef.current[i]!, promptSections }

        try {
          await askLLM(
            llmEngine,
            prompt,
            (text) => setPositions((prev) => {
              const n = [...prev]
              if (n[i]) n[i] = { ...n[i]!, commentary: text }
              return n
            }),
            abort.signal,
          )
        } catch (e) {
          if (!abort.signal.aborted) console.warn(`LLM failed for position ${i}:`, e)
        }

        setCommentaryProgress(i + 1)
      }
    }

    setPhase('done')
    setAnalyzing(false)
  }, [pgnInput, engineState, analyze, llmEngine])

  // Keyboard navigation
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === 'TEXTAREA') return
      if (e.key === 'ArrowLeft')  setCurrentIdx((i) => Math.max(0, i - 1))
      if (e.key === 'ArrowRight') setCurrentIdx((i) => Math.min(positions.length - 1, i + 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [positions.length])

  const arrows: Arrow[] = []
  if (current?.uci) {
    arrows.push({ startSquare: current.uci.slice(0, 2), endSquare: current.uci.slice(2, 4), color: 'rgba(30,120,230,0.75)' })
  }
  if (current?.bestMoveUci && current.bestMoveUci !== current.uci) {
    arrows.push({ startSquare: current.bestMoveUci.slice(0, 2), endSquare: current.bestMoveUci.slice(2, 4), color: 'rgba(0,190,80,0.85)' })
  }

  const total = positions.length

  return (
    <div className="app">
      {llmLoading && <LoadProgress text={llmProgressText} progress={llmProgress} />}

      <header className="app-header">
        <h1>♟ Chess Analyzer</h1>
        <span className="subtitle">ShashChess · AI Commentary</span>
        {engineState === 'unavailable' && (
          <span className="engine-status unavailable" title={engineError ?? ''}>
            Engine unavailable: {engineError ?? 'unknown error'}
          </span>
        )}
        {engineState === 'loading' && (
          <details className="engine-status loading">
            <summary>Engine loading… {engineLog}</summary>
            <pre style={{ fontSize: '11px', maxHeight: '200px', overflow: 'auto', textAlign: 'left', margin: '4px 0 0', whiteSpace: 'pre-wrap' }}>
              {debugLines.join('\n')}
            </pre>
          </details>
        )}
      </header>

      <div className="input-section">
        <textarea
          className="pgn-input"
          value={pgnInput}
          onChange={(e) => setPgnInput(e.target.value)}
          placeholder="Paste PGN or FEN here…"
          rows={4}
          disabled={analyzing}
        />
        <button
          className="analyze-btn"
          onClick={handleAnalyze}
          disabled={analyzing || !pgnInput.trim() || engineState !== 'ready'}
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
              <div className="progress-fill engine"
                style={{ width: `${total ? (engineProgress / total) * 100 : 0}%` }} />
            </div>
          </div>
          {phase === 'commentary' && (
            <div className="progress-item">
              <span>Commentary: {commentaryProgress}/{total}</span>
              <div className="progress-bar">
                <div className="progress-fill commentary"
                  style={{ width: `${total ? (commentaryProgress / total) * 100 : 0}%` }} />
              </div>
            </div>
          )}
        </div>
      )}

      {positions.length > 0 && current && (
        <div className="main-layout">
          <div className="board-section">
            <div className="board-with-eval">
              <EvalBar evalCp={current.evalCp} evalMate={current.evalMate} height={BOARD_SIZE} />
              <Board fen={current.fen} arrows={arrows} boardWidth={BOARD_SIZE} />
            </div>

            {positions.length > 1 ? (
              <div className="nav-controls">
                <button className="nav-btn" onClick={() => setCurrentIdx(0)} disabled={currentIdx === 0}>⏮</button>
                <button className="nav-btn" onClick={() => setCurrentIdx((i) => Math.max(0, i - 1))} disabled={currentIdx === 0}>◀</button>
                <span className="move-counter">
                  {currentIdx === 0
                    ? `Start / ${positions.length - 1} moves`
                    : `Move ${currentIdx} / ${positions.length - 1}`}
                </span>
                <button className="nav-btn" onClick={() => setCurrentIdx((i) => Math.min(positions.length - 1, i + 1))} disabled={currentIdx >= positions.length - 1}>▶</button>
                <button className="nav-btn" onClick={() => setCurrentIdx(positions.length - 1)} disabled={currentIdx >= positions.length - 1}>⏭</button>
              </div>
            ) : (
              <div className="nav-controls">
                <span className="move-counter" style={{ color: 'var(--text-dim)' }}>
                  Single position — paste PGN to navigate moves
                </span>
              </div>
            )}

            <div className="legend">
              <div className="legend-item"><div className="legend-arrow played" /><span>Played move</span></div>
              <div className="legend-item"><div className="legend-arrow best" /><span>Engine best</span></div>
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
