import { evalToPercent, formatEval } from '../utils/eval.js'

export default function EvalBar({ evalCp, evalMate, height = 520 }) {
  const whitePct    = evalToPercent(evalCp, evalMate)
  const blackPct    = 100 - whitePct
  const { text }    = formatEval(evalCp, evalMate, true)   // short = one decimal
  const whiteWins   = evalMate != null ? evalMate > 0 : (evalCp ?? 0) >= 0

  return (
    <div className="eval-bar" style={{ height }}>
      <div className="eval-segment-black" style={{ flex: blackPct }} />
      <div className="eval-segment-white" style={{ flex: whitePct }} />
      <span className={`eval-bar-label ${whiteWins ? 'bottom' : 'top'}`}>{text}</span>
    </div>
  )
}
