import { retrieve } from './retriever'
import { promptDescription } from './shashin'
import type { ShashinType, PromptSection } from '../types'

const LEVEL_INSTRUCTIONS: Record<string, string> = {
  beginner:     'Use simple language, avoid chess jargon.',
  intermediate: 'Brief technical terms are fine.',
  advanced:     'Use chess terminology freely.',
}

const QUESTION_TEMPLATES: Record<string, string> = {
  best_move: 'What is the best move and why? Compare it to the move actually played in the game.',
  explain:   'Explain the current position and evaluate the move played versus the engine\'s recommendation.',
  plan:      'What is the strategic plan for the side to move? Discuss whether the move played fits that plan or if the engine\'s suggestion is superior.',
}

function moveQualityLabel(
  played: string | null,
  bestSan: string | null,
  scoreCp: number | null,
): string {
  if (!played) return ''
  if (played === bestSan) return 'best move'
  if (scoreCp === null) return 'alternative'
  const delta = Math.abs(scoreCp)
  if (delta < 20) return 'excellent'
  if (delta < 50) return 'good'
  if (delta < 100) return 'inaccuracy'
  if (delta < 200) return 'mistake'
  return 'blunder'
}

function evalStr(
  scoreCp: number | null,
  mateIn: number | null,
  wdlWin: number,
  wdlDraw: number,
): string {
  if (mateIn !== null) {
    return `Forced checkmate in ${mateIn} move${mateIn !== 1 ? 's' : ''}`
  }
  if (scoreCp === null) return 'Equal position'
  const sign = scoreCp >= 0 ? '+' : ''
  const pawns = scoreCp / 100
  const winPct = Math.round(wdlWin / 10)
  const drawPct = Math.round(wdlDraw / 10)
  const side = scoreCp >= 0 ? 'White' : 'Black'
  return `${side} is better by ${sign}${pawns.toFixed(1)} pawns (${winPct}% win, ${drawPct}% draw)`
}

export function buildPrompt(params: {
  fen: string
  scoreCp: number | null
  mateIn: number | null
  wdlWin: number
  wdlDraw: number
  wdlLoss?: number
  bestMoveSan: string | null
  shashinType: ShashinType
  sideToMove: 'white' | 'black'
  movesHistory: string[]
  playedMove: string | null
  level: string
  question: string
}): string {
  const {
    fen, scoreCp, mateIn, wdlWin, wdlDraw,
    bestMoveSan, shashinType, sideToMove,
    movesHistory, playedMove, level, question,
  } = params

  const evalText = evalStr(scoreCp, mateIn, wdlWin, wdlDraw)
  const movesStr = movesHistory.slice(-5).join(' ') || 'none'
  const levelHint = LEVEL_INSTRUCTIONS[level] ?? LEVEL_INSTRUCTIONS.intermediate
  const questionText = QUESTION_TEMPLATES[question] ?? question

  const theoryChunks = retrieve(fen, shashinType, question, mateIn, playedMove, bestMoveSan)
  const theoryText = theoryChunks.map((c) => `- ${c}`).join('\n')

  const playedLine = playedMove ? `  Move played: ${playedMove}\n` : ''
  const qualityLabel = moveQualityLabel(playedMove, bestMoveSan, scoreCp)
  const qualityLine = qualityLabel ? `  Move quality: ${qualityLabel}\n` : ''

  let comparisonBlock = ''
  if (playedMove && bestMoveSan && playedMove !== bestMoveSan) {
    comparisonBlock = `  Move comparison: The game continued with ${playedMove}, but the engine recommends ${bestMoveSan} as stronger. In your answer, explain WHY ${bestMoveSan} is better than ${playedMove}.\n`
  } else if (playedMove && bestMoveSan) {
    comparisonBlock = `  Move comparison: The move played (${playedMove}) matches the engine's best move. Explain what makes it the strongest choice.\n`
  }

  return [
    `You are a chess coach. ${levelHint} Answer the question in 2-3 sentences. Be specific — mention the best move by name.`,
    '',
    'Chess theory context:',
    theoryText,
    '',
    'Position info:',
    `  Recent moves: ${movesStr}`,
    playedLine.trimEnd(),
    qualityLine.trimEnd(),
    `  Side to move: ${sideToMove.charAt(0).toUpperCase() + sideToMove.slice(1)}`,
    `  Engine evaluation: ${evalText}`,
    `  Best move: ${bestMoveSan ?? 'unknown'}`,
    `  Position style: ${promptDescription(shashinType)}`,
    comparisonBlock.trimEnd(),
    '',
    `Question: ${questionText}`,
  ]
    .filter((l) => l !== undefined)
    .join('\n')
}

export function buildPromptSections(params: Parameters<typeof buildPrompt>[0]): PromptSection[] {
  const {
    scoreCp, mateIn, wdlWin, wdlDraw,
    bestMoveSan, shashinType, sideToMove,
    movesHistory, playedMove, level, question,
    fen,
  } = params

  const evalText = evalStr(scoreCp, mateIn, wdlWin, wdlDraw)
  const movesStr = movesHistory.slice(-5).join(' ') || 'none'
  const levelHint = LEVEL_INSTRUCTIONS[level] ?? LEVEL_INSTRUCTIONS.intermediate
  const questionText = QUESTION_TEMPLATES[question] ?? question

  const theoryChunks = retrieve(fen, shashinType, question, mateIn, playedMove, bestMoveSan)
  const theoryText = theoryChunks.map((c) => `- ${c}`).join('\n') || '(none)'

  const playedLine = playedMove ? `  Move played: ${playedMove}` : ''
  const qualityLabel = moveQualityLabel(playedMove, bestMoveSan, scoreCp)
  const qualityLine = qualityLabel ? `  Move quality: ${qualityLabel}` : ''

  let comparisonBlock = ''
  if (playedMove && bestMoveSan && playedMove !== bestMoveSan) {
    comparisonBlock = `Game continued with ${playedMove}, engine recommends ${bestMoveSan}. Explain WHY ${bestMoveSan} is better.`
  } else if (playedMove && bestMoveSan) {
    comparisonBlock = `${playedMove} matches the engine's best move. Explain what makes it strongest.`
  }

  return [
    {
      label: 'System instruction',
      content: `You are a chess coach. ${levelHint} Answer in 2-3 sentences. Be specific — mention the best move by name.`,
    },
    {
      label: 'Chess theory',
      content: theoryText,
    },
    {
      label: 'Position info',
      content: [
        `Recent moves: ${movesStr}`,
        playedLine,
        qualityLine,
        `Side to move: ${sideToMove.charAt(0).toUpperCase() + sideToMove.slice(1)}`,
        `Engine evaluation: ${evalText}`,
        `Best move: ${bestMoveSan ?? 'unknown'}`,
        `Position style: ${promptDescription(shashinType)}`,
      ].filter(Boolean).join('\n'),
    },
    comparisonBlock ? { label: 'Move comparison', content: comparisonBlock } : null,
    {
      label: 'Question',
      content: questionText,
    },
  ].filter(Boolean) as PromptSection[]
}
