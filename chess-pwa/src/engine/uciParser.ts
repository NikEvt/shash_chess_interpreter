import { Chess } from 'chess.js'
import { getShashinType } from '../agent/shashin'
import type { EngineResult } from '../types'

// Parse UCI "info depth ... score cp ... wdl ... pv ..." line
// fen parameter is kept for future use (e.g. side-to-move normalization at parse time)
export function parseInfoLine(line: string, _fen: string): Partial<EngineResult> | null {
  if (!line.startsWith('info') || !line.includes('depth')) return null

  const depth = parseInt(line.match(/\bdepth\s+(\d+)/)?.[1] ?? '0', 10)

  let scoreCp: number | null = null
  let mateIn: number | null = null
  const scoreMatch = line.match(/\bscore\s+(cp|mate)\s+(-?\d+)/)
  if (scoreMatch) {
    if (scoreMatch[1] === 'cp') scoreCp = parseInt(scoreMatch[2], 10)
    else mateIn = parseInt(scoreMatch[2], 10)
  }

  // WDL: "wdl W D L" (each 0–1000, sum=1000)
  let wdlWin = 500, wdlDraw = 0, wdlLoss = 500
  const wdlMatch = line.match(/\bwdl\s+(\d+)\s+(\d+)\s+(\d+)/)
  if (wdlMatch) {
    wdlWin = parseInt(wdlMatch[1], 10)
    wdlDraw = parseInt(wdlMatch[2], 10)
    wdlLoss = parseInt(wdlMatch[3], 10)
  }

  // PV
  const pvMatch = line.match(/\bpv\s+(.+)$/)
  const pvUci = pvMatch ? pvMatch[1].trim().split(/\s+/) : []

  return { depth, scoreCp, mateIn, wdlWin, wdlDraw, wdlLoss, pvUci }
}

// Parse "bestmove e2e4 [ponder ...]" line
export function parseBestMove(line: string): string | null {
  const m = line.match(/^bestmove\s+(\S+)/)
  return m ? m[1] : null
}

// Convert UCI move (e2e4) to SAN given a FEN
export function uciToSan(fen: string, uciMove: string): string {
  try {
    const chess = new Chess(fen)
    const from = uciMove.slice(0, 2)
    const to = uciMove.slice(2, 4)
    const promotion = uciMove.length === 5 ? uciMove[4] as 'q' | 'r' | 'b' | 'n' : undefined
    const result = chess.move({ from, to, promotion })
    return result?.san ?? uciMove
  } catch {
    return uciMove
  }
}

// Convert PV UCI moves to SAN array
export function pvToSan(fen: string, pvUci: string[]): string[] {
  const sans: string[] = []
  try {
    const chess = new Chess(fen)
    for (const mv of pvUci.slice(0, 8)) {
      const from = mv.slice(0, 2)
      const to = mv.slice(2, 4)
      const promotion = mv.length === 5 ? mv[4] as 'q' | 'r' | 'b' | 'n' : undefined
      const result = chess.move({ from, to, promotion })
      if (!result) break
      sans.push(result.san)
    }
  } catch { /* ignore */ }
  return sans
}

// Build complete EngineResult from parsed info + bestmove
export function buildEngineResult(params: {
  fen: string
  bestMoveUci: string
  scoreCp: number | null
  mateIn: number | null
  wdlWin: number
  wdlDraw: number
  wdlLoss: number
  depth: number
  pvUci: string[]
}): EngineResult {
  const { fen, bestMoveUci, scoreCp, mateIn, wdlWin, wdlDraw, wdlLoss, depth, pvUci } = params

  const chess = new Chess(fen)
  const sideToMove = chess.turn() === 'w' ? 'white' : 'black'

  // Normalize scoreCp to always be from White's perspective
  const scoreCpWhite = scoreCp !== null
    ? (sideToMove === 'black' ? -scoreCp : scoreCp)
    : null

  // WDL is from side-to-move perspective; normalize to White
  const [normWin, normLoss] = sideToMove === 'black'
    ? [wdlLoss, wdlWin]
    : [wdlWin, wdlLoss]

  return {
    fen,
    bestMoveUci,
    bestMoveSan: uciToSan(fen, bestMoveUci),
    scoreCp: scoreCpWhite,
    mateIn: mateIn !== null ? (sideToMove === 'black' ? -mateIn : mateIn) : null,
    wdlWin: normWin,
    wdlDraw,
    wdlLoss: normLoss,
    depth,
    shashinType: getShashinType(scoreCpWhite),
    sideToMove,
    pvUci: pvUci.slice(0, 8),
    pvSan: pvToSan(fen, pvUci),
  }
}
