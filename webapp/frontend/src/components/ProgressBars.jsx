export default function ProgressBars({ phase, engineProgress, commentaryProgress, total }) {
  if (phase === 'idle' || phase === 'done') return null

  const enginePct     = total ? (engineProgress / total) * 100 : 0
  const commentaryPct = total ? (commentaryProgress / total) * 100 : 0

  return (
    <div className="progress-section">
      <ProgressItem label={`Engine: ${engineProgress}/${total}`} pct={enginePct} cls="engine" />
      {phase === 'commentary' && (
        <ProgressItem label={`Commentary: ${commentaryProgress}/${total}`} pct={commentaryPct} cls="commentary" />
      )}
    </div>
  )
}

function ProgressItem({ label, pct, cls }) {
  return (
    <div className="progress-item">
      <span>{label}</span>
      <div className="progress-bar">
        <div className={`progress-fill ${cls}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
