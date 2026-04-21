import { QUALITY_SYMBOLS } from '../App.jsx'

function formatEval(cp, mate) {
  if (mate !== null && mate !== undefined) {
    return { text: mate > 0 ? `+M${Math.abs(mate)}` : `-M${Math.abs(mate)}`, cls: mate > 0 ? 'positive' : 'negative' }
  }
  if (cp === null || cp === undefined) return { text: '–', cls: 'equal' }
  const v = cp / 100
  return {
    text: (v >= 0 ? '+' : '') + v.toFixed(2),
    cls: v > 0.1 ? 'positive' : v < -0.1 ? 'negative' : 'equal',
  }
}

const QUALITY_BADGE_CLASS = {
  blunder: 'qb-blunder',
  mistake: 'qb-mistake',
  inaccuracy: 'qb-inaccuracy',
  good: 'qb-good',
  excellent: 'qb-excellent',
  best: 'qb-best',
  book: 'qb-book',
}

const QUALITY_LABEL = {
  blunder: 'Blunder',
  mistake: 'Mistake',
  inaccuracy: 'Inaccuracy',
  good: 'Good',
  excellent: 'Excellent',
  best: 'Best move',
  book: 'Opening',
}

export default function Commentary({ position }) {
  if (!position) return null

  const { san, color, move_number, quality, eval_cp, eval_mate, eval_loss_cp,
          best_move_san, pv_san, commentary } = position

  const evalFmt = formatEval(eval_cp, eval_mate)

  const moveLabel = san
    ? `${move_number}${color === 'white' ? '.' : '…'} ${san}`
    : 'Starting position'

  const sym = QUALITY_SYMBOLS[quality] ?? ''
  const badgeCls = QUALITY_BADGE_CLASS[quality] ?? 'qb-good'
  const qualLabel = QUALITY_LABEL[quality] ?? quality

  return (
    <div className="commentary-panel">
      <div className="commentary-header">
        <span className="commentary-move-label">{moveLabel}</span>
        {sym && <span style={{ fontSize: 14, fontWeight: 700 }}>{sym}</span>}
        <span className={`quality-badge ${badgeCls}`}>{qualLabel}</span>
      </div>

      <div className="commentary-body">
        {/* Eval */}
        <div className="eval-row">
          <span>Eval:</span>
          <span className={`eval-value ${evalFmt.cls}`}>{evalFmt.text}</span>
          {eval_loss_cp !== null && eval_loss_cp !== undefined && eval_loss_cp > 0 && (
            <>
              <span className="eval-arrow">▼</span>
              <span className="eval-loss-badge">−{(eval_loss_cp / 100).toFixed(2)}</span>
            </>
          )}
        </div>

        {/* Best move */}
        {best_move_san && best_move_san !== san && (
          <div className="best-move-row">
            <span>Best:</span>
            <span className="best-move-san">{best_move_san}</span>
          </div>
        )}

        {/* Commentary text */}
        {commentary
          ? <p className="commentary-text">{commentary}</p>
          : <p className="commentary-loading">Generating commentary…</p>
        }

        {/* Principal variation */}
        {pv_san && pv_san.length > 0 && (
          <div className="pv-section">
            <div className="pv-label">Engine line</div>
            <div className="pv-moves">{pv_san.join(' ')}</div>
          </div>
        )}
      </div>
    </div>
  )
}
