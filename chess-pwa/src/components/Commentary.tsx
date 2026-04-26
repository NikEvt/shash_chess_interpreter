import { useState } from 'react'
import type { Position, MoveQuality } from '../types'

const QUALITY_SYMBOLS: Record<MoveQuality, string> = {
  blunder: '??', mistake: '?', inaccuracy: '?!',
  good: '', excellent: '!', best: '✓', book: '',
}

const QUALITY_BADGE_CLASS: Record<MoveQuality, string> = {
  blunder: 'qb-blunder', mistake: 'qb-mistake', inaccuracy: 'qb-inaccuracy',
  good: 'qb-good', excellent: 'qb-excellent', best: 'qb-best', book: 'qb-book',
}

const QUALITY_LABEL: Record<MoveQuality, string> = {
  blunder: 'Blunder', mistake: 'Mistake', inaccuracy: 'Inaccuracy',
  good: 'Good', excellent: 'Excellent', best: 'Best move', book: 'Opening',
}

function formatEval(cp: number | null, mate: number | null) {
  if (mate !== null && mate !== undefined) {
    return { text: mate > 0 ? `+M${Math.abs(mate)}` : `-M${Math.abs(mate)}`, cls: mate > 0 ? 'positive' : 'negative' }
  }
  if (cp === null) return { text: '–', cls: 'equal' }
  const v = cp / 100
  return {
    text: (v >= 0 ? '+' : '') + v.toFixed(2),
    cls: v > 0.1 ? 'positive' : v < -0.1 ? 'negative' : 'equal',
  }
}

interface Props {
  position: Position | null
}

export default function Commentary({ position }: Props) {
  const [debugOpen, setDebugOpen] = useState(false)
  const [openSection, setOpenSection] = useState<number | null>(null)

  if (!position) return null

  const { san, color, moveNumber, quality, evalCp, evalMate, evalLossCp,
          bestMoveSan, pvSan, commentary, shashinType,
          rawEngineLines, promptSections } = position

  const evalFmt = formatEval(evalCp, evalMate)
  const moveLabel = san
    ? `${moveNumber}${color === 'white' ? '.' : '…'} ${san}`
    : 'Starting position'

  const sym = quality ? (QUALITY_SYMBOLS[quality] ?? '') : ''
  const badgeCls = quality ? (QUALITY_BADGE_CLASS[quality] ?? 'qb-good') : 'qb-good'
  const qualLabel = quality ? (QUALITY_LABEL[quality] ?? quality) : ''

  return (
    <div className="commentary-panel">
      <div className="commentary-header">
        <span className="commentary-move-label">{moveLabel}</span>
        {sym && <span style={{ fontSize: 14, fontWeight: 700 }}>{sym}</span>}
        {qualLabel && <span className={`quality-badge ${badgeCls}`}>{qualLabel}</span>}
        {shashinType && (
          <span className={`shashin-badge shashin-${shashinType.toLowerCase()}`}>
            {shashinType}
          </span>
        )}
      </div>

      <div className="commentary-body">
        <div className="eval-row">
          <span>Eval:</span>
          <span className={`eval-value ${evalFmt.cls}`}>{evalFmt.text}</span>
          {evalLossCp !== null && evalLossCp !== undefined && evalLossCp > 0 && (
            <>
              <span className="eval-arrow">▼</span>
              <span className="eval-loss-badge">−{(evalLossCp / 100).toFixed(2)}</span>
            </>
          )}
        </div>

        {bestMoveSan && bestMoveSan !== san && (
          <div className="best-move-row">
            <span>Best:</span>
            <span className="best-move-san">{bestMoveSan}</span>
          </div>
        )}

        {commentary
          ? <p className="commentary-text">{commentary}</p>
          : <p className="commentary-loading">Generating commentary…</p>
        }

        {pvSan && pvSan.length > 0 && (
          <div className="pv-section">
            <div className="pv-label">Engine line</div>
            <div className="pv-moves">{pvSan.join(' ')}</div>
          </div>
        )}
      </div>

      {(rawEngineLines?.length || promptSections?.length) ? (
        <div className="debug-panel">
          <button
            className="debug-toggle"
            onClick={() => setDebugOpen((o) => !o)}
          >
            {debugOpen ? '▾' : '▸'} Debug: engine output & prompt
          </button>

          {debugOpen && (
            <div className="debug-body">

              {rawEngineLines && rawEngineLines.length > 0 && (
                <div className="debug-section">
                  <div className="debug-section-title">Engine UCI output ({rawEngineLines.length} lines)</div>
                  <pre className="debug-pre engine-output">
                    {rawEngineLines.join('\n')}
                  </pre>
                </div>
              )}

              {promptSections && promptSections.length > 0 && (
                <div className="debug-section">
                  <div className="debug-section-title">LLM prompt ({promptSections.length} sections)</div>
                  {promptSections.map((sec, idx) => (
                    <div key={idx} className="prompt-section">
                      <button
                        className="prompt-section-header"
                        onClick={() => setOpenSection(openSection === idx ? null : idx)}
                      >
                        <span className="prompt-section-num">{idx + 1}</span>
                        <span className="prompt-section-label">{sec.label}</span>
                        <span className="prompt-section-chevron">{openSection === idx ? '▾' : '▸'}</span>
                      </button>
                      {openSection === idx && (
                        <pre className="debug-pre prompt-content">{sec.content}</pre>
                      )}
                    </div>
                  ))}
                </div>
              )}

            </div>
          )}
        </div>
      ) : null}
    </div>
  )
}
