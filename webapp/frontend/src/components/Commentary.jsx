import { useState } from 'react'
import { QUALITY_SYMBOLS, QUALITY_BADGE_CLASS, QUALITY_LABEL } from '../constants.js'
import { formatEval } from '../utils/eval.js'

/**
 * Format engine PV with proper move numbers and side indicators.
 *
 * @param {string[]} pvSan     - array of SAN moves starting from the current position
 * @param {number}   moveNumber - fullmove number of the position (move that was just played)
 * @param {string|null} color  - "white" | "black" | null (null = starting position)
 *
 * Examples:
 *   after 1.e4 (color="white", moveNumber=1): "1… e5 2. Nf3 Nc6"
 *   after 1…e5 (color="black", moveNumber=1): "2. Nf3 Nc6 3. Bb5"
 */
function formatPV(pvSan, moveNumber, color) {
  if (!pvSan?.length) return null

  // Who is to move NEXT in this position
  const whiteMovesFirst = !color || color === 'black'
  // Starting move number for the PV
  let num = !color ? 1 : color === 'white' ? moveNumber : moveNumber + 1
  let isWhite = whiteMovesFirst

  return pvSan.map((san, i) => {
    let prefix = null
    if (isWhite) {
      prefix = <span key={`n${i}`} className="pv-num">{num}.</span>
    } else if (i === 0) {
      // First move is Black's — need the "N…" prefix to signal Black to move
      prefix = <span key={`n${i}`} className="pv-num">{num}…</span>
    }
    if (!isWhite) num++
    isWhite = !isWhite
    return (
      <span key={i} className="pv-token">
        {prefix}
        <span className="pv-move">{san}</span>
      </span>
    )
  })
}

export default function Commentary({ position }) {
  const [debugOpen,    setDebugOpen]    = useState(false)
  const [openSection,  setOpenSection]  = useState(null)

  if (!position) return null

  const {
    san, color, move_number, quality,
    eval_cp, eval_mate, eval_loss_cp,
    best_move_san, pv_san, commentary,
    engine_summary, prompt_sections, full_prompt, config_preset,
  } = position

  const evalFmt   = formatEval(eval_cp, eval_mate)
  const moveLabel = san
    ? `${move_number}${color === 'white' ? '.' : '…'} ${san}`
    : 'Starting position'

  const sym       = QUALITY_SYMBOLS[quality]     ?? ''
  const badgeCls  = QUALITY_BADGE_CLASS[quality] ?? 'qb-good'
  const qualLabel = QUALITY_LABEL[quality]       ?? quality

  const pvTokens  = formatPV(pv_san, move_number, color)

  return (
    <div className="commentary-panel">

      <div className="commentary-header">
        <span className="commentary-move-label">{moveLabel}</span>
        {sym && <span style={{ fontSize: 14, fontWeight: 700 }}>{sym}</span>}
        <span className={`quality-badge ${badgeCls}`}>{qualLabel}</span>
      </div>

      <div className="commentary-body">

        <div className="eval-row">
          <span>Eval:</span>
          <span className={`eval-value ${evalFmt.cls}`}>{evalFmt.text}</span>
          {eval_loss_cp != null && eval_loss_cp > 0 && (
            <>
              <span className="eval-arrow">▼</span>
              <span className="eval-loss-badge">−{(eval_loss_cp / 100).toFixed(2)}</span>
            </>
          )}
        </div>

        {best_move_san && best_move_san !== san && (
          <div className="best-move-row">
            <span>Best:</span>
            <span className="best-move-san">{best_move_san}</span>
          </div>
        )}

        {commentary
          ? <p className="commentary-text">{commentary}</p>
          : <p className="commentary-loading">Generating commentary…</p>
        }

        {pvTokens && (
          <div className="pv-section">
            <div className="pv-label">Engine line</div>
            <div className="pv-moves">{pvTokens}</div>
          </div>
        )}

      </div>

      {(engine_summary?.length > 0 || prompt_sections?.length > 0 || full_prompt) && (
        <DebugPanel
          engineSummary={engine_summary}
          promptSections={prompt_sections}
          fullPrompt={full_prompt}
          configPreset={config_preset}
          open={debugOpen}
          onToggle={() => setDebugOpen(o => !o)}
          openSection={openSection}
          onSectionToggle={i => setOpenSection(openSection === i ? null : i)}
        />
      )}
    </div>
  )
}

function DebugPanel({ engineSummary, promptSections, fullPrompt, configPreset, open, onToggle, openSection, onSectionToggle }) {
  const [promptOpen, setPromptOpen] = useState(false)
  const sectionLabels = promptSections?.map(s => s.label) ?? []

  return (
    <div className="debug-panel">
      <button className="debug-toggle" onClick={onToggle}>
        {open ? '▾' : '▸'} Debug: engine output &amp; prompt
        {configPreset && (
          <span className="debug-config-badge">{configPreset}</span>
        )}
      </button>

      {open && (
        <div className="debug-body">

          {configPreset && sectionLabels.length > 0 && (
            <div className="debug-section">
              <div className="debug-section-title">
                Config: <span className="debug-config-name">{configPreset}</span>
                {' '}— {sectionLabels.length} active sections
              </div>
              <div className="debug-section-tags">
                {sectionLabels.map(label => (
                  <span key={label} className="debug-section-tag">{label}</span>
                ))}
              </div>
            </div>
          )}

          {engineSummary?.length > 0 && (
            <div className="debug-section">
              <div className="debug-section-title">
                Engine UCI output ({engineSummary.length} lines)
              </div>
              <pre className="debug-pre engine-output">{engineSummary.join('\n')}</pre>
            </div>
          )}

          {fullPrompt && (
            <div className="debug-section">
              <button className="prompt-section-header" onClick={() => setPromptOpen(o => !o)}>
                <span className="debug-section-title" style={{ margin: 0 }}>Full prompt (sent to LLM)</span>
                <span className="prompt-section-chevron">{promptOpen ? '▾' : '▸'}</span>
              </button>
              {promptOpen && (
                <pre className="debug-pre prompt-content prompt-full">{fullPrompt}</pre>
              )}
            </div>
          )}

          {promptSections?.length > 0 && (
            <div className="debug-section">
              <div className="debug-section-title">
                LLM prompt ({promptSections.length} sections)
              </div>
              {promptSections.map((sec, i) => (
                <div key={i} className="prompt-section">
                  <button className="prompt-section-header" onClick={() => onSectionToggle(i)}>
                    <span className="prompt-section-num">{i + 1}</span>
                    <span className="prompt-section-label">{sec.label}</span>
                    <span className="prompt-section-chevron">{openSection === i ? '▾' : '▸'}</span>
                  </button>
                  {openSection === i && (
                    <pre className="debug-pre prompt-content">{sec.content}</pre>
                  )}
                </div>
              ))}
            </div>
          )}

        </div>
      )}
    </div>
  )
}
