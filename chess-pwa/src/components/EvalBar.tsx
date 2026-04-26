function evalToPercent(cp: number | null, mate: number | null): number {
  if (mate !== null && mate !== undefined) return mate > 0 ? 100 : 0
  if (cp === null) return 50
  return 50 + 50 * (2 / Math.PI) * Math.atan(cp / 400)
}

function formatEval(cp: number | null, mate: number | null): string {
  if (mate !== null && mate !== undefined) {
    return mate > 0 ? `+M${Math.abs(mate)}` : `-M${Math.abs(mate)}`
  }
  if (cp === null) return '0.0'
  const v = cp / 100
  return (v >= 0 ? '+' : '') + v.toFixed(1)
}

interface Props {
  evalCp: number | null
  evalMate: number | null
  height?: number
}

export default function EvalBar({ evalCp, evalMate, height = 520 }: Props) {
  const whitePct = evalToPercent(evalCp, evalMate)
  const blackPct = 100 - whitePct
  const text = formatEval(evalCp, evalMate)
  const whiteWinning = evalMate !== null ? evalMate > 0 : (evalCp ?? 0) >= 0

  return (
    <div className="eval-bar" style={{ height }}>
      <div className="eval-segment-black" style={{ flex: blackPct }} />
      <div className="eval-segment-white" style={{ flex: whitePct }} />
      {whiteWinning
        ? <span className="eval-bar-label bottom">{text}</span>
        : <span className="eval-bar-label top">{text}</span>
      }
    </div>
  )
}
