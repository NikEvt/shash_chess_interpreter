import { CHUNKS } from './knowledgeBase'
import { BM25 } from './bm25'
import type { ShashinType } from '../types'

const _bm25 = new BM25(CHUNKS.map((c) => c.text))

const QUESTION_KEYWORDS: Record<string, string> = {
  best_move: 'best move plan tactics',
  explain:   'explain position evaluation advantage',
  plan:      'strategic plan strategy long-term',
}

const SHASHIN_KEYWORDS: Record<ShashinType, string> = {
  Capablanca: 'strategic positional balanced open file weak square outpost plan',
  Tal:        'tactical attack sacrifice king safety kingside initiative',
  Petrosian:  'defensive prophylaxis exchange blockade fortress solid draw',
}

const PHASE_KEYWORDS: Record<string, string> = {
  opening:    'opening development center castle',
  middlegame: 'plan strategy middlegame attack',
  endgame:    'endgame king pawn promotion rook',
}

function positionPhase(fen: string): string {
  const board = fen.split(' ')[0]
  const pieceCount = (board.match(/[a-zA-Z]/g) ?? []).length
  if (pieceCount >= 28) return 'opening'
  if (pieceCount <= 14) return 'endgame'
  return 'middlegame'
}

function buildQuery(
  fen: string,
  shashinType: ShashinType,
  question: string,
  mateIn: number | null,
  playedMove: string | null,
  bestMoveSan: string | null,
): string[] {
  const tokens: string[] = []
  tokens.push(...(QUESTION_KEYWORDS[question] ?? '').split(' ').filter(Boolean))
  tokens.push(...(SHASHIN_KEYWORDS[shashinType] ?? '').split(' ').filter(Boolean))
  tokens.push(...(PHASE_KEYWORDS[positionPhase(fen)] ?? '').split(' ').filter(Boolean))
  if (mateIn !== null) tokens.push('tactics', 'checkmate', 'forced')
  if (playedMove && bestMoveSan && playedMove !== bestMoveSan) {
    tokens.push('mistake', 'inaccuracy', 'alternative', 'better')
  }
  return tokens
}

export function retrieve(
  fen: string,
  shashinType: ShashinType,
  question: string,
  mateIn: number | null,
  playedMove: string | null,
  bestMoveSan: string | null,
  topK = 2,
): string[] {
  const query = buildQuery(fen, shashinType, question, mateIn, playedMove, bestMoveSan)
  const scores = _bm25.getScores(query.join(' '))
  return scores
    .map((s, i) => ({ s, i }))
    .sort((a, b) => b.s - a.s)
    .slice(0, topK)
    .map(({ i }) => CHUNKS[i].text)
}
