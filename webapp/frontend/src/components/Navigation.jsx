export default function Navigation({ currentIdx, total, nav }) {
  const atStart = currentIdx === 0
  const atEnd   = currentIdx >= total - 1

  if (total <= 1) {
    return (
      <div className="nav-controls">
        <span className="move-counter" style={{ color: 'var(--text-dim)' }}>
          Single position — paste PGN to navigate moves
        </span>
      </div>
    )
  }

  return (
    <div className="nav-controls">
      <button className="nav-btn" onClick={nav.toStart} disabled={atStart}>⏮</button>
      <button className="nav-btn" onClick={nav.prev}    disabled={atStart}>◀</button>
      <span className="move-counter">
        {currentIdx === 0
          ? `Start / ${total - 1} moves`
          : `Move ${currentIdx} / ${total - 1}`}
      </span>
      <button className="nav-btn" onClick={nav.next}  disabled={atEnd}>▶</button>
      <button className="nav-btn" onClick={nav.toEnd} disabled={atEnd}>⏭</button>
    </div>
  )
}
