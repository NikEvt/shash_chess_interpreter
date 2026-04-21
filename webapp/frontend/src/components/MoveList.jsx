import { useEffect, useRef } from 'react'
import { QUALITY_SYMBOLS } from '../App.jsx'

const QUALITY_SYMBOL_CLASS = {
  blunder: 'q-blunder',
  mistake: 'q-mistake',
  inaccuracy: 'q-inaccuracy',
  excellent: 'q-excellent',
  best: 'q-best',
}

const QUALITY_BG_CLASS = {
  blunder: 'q-bg-blunder',
  mistake: 'q-bg-mistake',
  inaccuracy: 'q-bg-inaccuracy',
}

function groupMoves(positions) {
  const rows = []
  for (let i = 1; i < positions.length; i++) {
    const pos = positions[i]
    if (!pos) continue
    if (pos.color === 'white') {
      rows.push({ moveNum: pos.move_number, white: { ...pos, idx: i }, black: null })
    } else {
      const last = rows[rows.length - 1]
      if (last && last.black === null && last.white !== null) {
        last.black = { ...pos, idx: i }
      } else {
        rows.push({ moveNum: pos.move_number, white: null, black: { ...pos, idx: i } })
      }
    }
  }
  return rows
}

function MoveCell({ pos, isActive, onClick }) {
  if (!pos) return <div className="move-cell" />

  const sym = QUALITY_SYMBOLS[pos.quality] ?? ''
  const symClass = QUALITY_SYMBOL_CLASS[pos.quality] ?? ''
  const bgClass = QUALITY_BG_CLASS[pos.quality] ?? ''

  return (
    <div
      className={`move-cell ${isActive ? 'active' : ''} ${!isActive && bgClass ? bgClass : ''} ${pos.san ? '' : 'loading'}`}
      onClick={onClick}
    >
      <span className="move-san">{pos.san ?? '…'}</span>
      {sym && <span className={`quality-symbol ${isActive ? '' : symClass}`}>{sym}</span>}
    </div>
  )
}

export default function MoveList({ positions, currentIdx, onSelect }) {
  const rows = groupMoves(positions)
  const activeRowRef = useRef(null)

  useEffect(() => {
    activeRowRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [currentIdx])

  return (
    <div className="move-list-panel">
      <div className="move-list-header">Moves</div>
      <div className="move-list-scroll">
        {rows.map((row, ri) => {
          const wActive = row.white?.idx === currentIdx
          const bActive = row.black?.idx === currentIdx
          return (
            <div
              className="move-row"
              key={ri}
              ref={wActive || bActive ? activeRowRef : null}
            >
              <span className="move-num">{row.moveNum}.</span>
              <MoveCell
                pos={row.white}
                isActive={wActive}
                onClick={() => row.white && onSelect(row.white.idx)}
              />
              <MoveCell
                pos={row.black}
                isActive={bActive}
                onClick={() => row.black && onSelect(row.black.idx)}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
