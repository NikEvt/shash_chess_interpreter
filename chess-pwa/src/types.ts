export type ShashinType = 'Tal' | 'Capablanca' | 'Petrosian'
export type MoveQuality = 'blunder' | 'mistake' | 'inaccuracy' | 'good' | 'excellent' | 'best' | 'book'

export interface PromptSection {
  label: string
  content: string
}

export interface EngineResult {
  fen: string
  bestMoveUci: string
  bestMoveSan: string
  scoreCp: number | null
  mateIn: number | null
  wdlWin: number
  wdlDraw: number
  wdlLoss: number
  depth: number
  shashinType: ShashinType
  sideToMove: 'white' | 'black'
  pvUci: string[]
  pvSan: string[]
  rawLines?: string[]
}

export interface Position {
  fen: string
  san: string | null
  uci: string | null
  color: 'white' | 'black' | null
  moveNumber: number | null
  evalCp: number | null
  evalMate: number | null
  evalLossCp: number | null
  bestMoveSan: string | null
  bestMoveUci: string | null
  pvSan: string[]
  quality: MoveQuality | null
  shashinType: ShashinType | null
  commentary: string | null
  movesHistory: string[]
  rawEngineLines?: string[]
  promptSections?: PromptSection[]
}
