function evalToPercent(cp, mate) {
  if (mate !== null && mate !== undefined) return mate > 0 ? 100 : 0
  if (cp === null || cp === undefined) return 50
  return 50 + 50 * (2 / Math.PI) * Math.atan(cp / 400)
}

function formatEval(cp, mate) {
  if (mate !== null && mate !== undefined) {
    return mate > 0 ? `+M${Math.abs(mate)}` : `-M${Math.abs(mate)}`
  }
  if (cp === null || cp === undefined) return '0.0'
  const v = cp / 100
  return (v >= 0 ? '+' : '') + v.toFixed(1)
}

export default function EvalBar({ evalCp, evalMate, height = 520 }) {
  const whitePct = evalToPercent(evalCp, evalMate)
  const blackPct = 100 - whitePct
  const text = formatEval(evalCp, evalMate)
  const whiteWinning = (evalCp ?? 0) >= 0 && evalMate !== null ? evalMate > 0 : (evalCp ?? 0) >= 0

  return (
    <div className="eval-bar" style={{ height }}>
      <div
        className="eval-segment-black"
        style={{ flex: blackPct }}
      />
      <div
        className="eval-segment-white"
        style={{ flex: whitePct }}
      />
      {whiteWinning
        ? <span className="eval-bar-label bottom">{text}</span>
        : <span className="eval-bar-label top">{text}</span>
      }
    </div>
  )
}
