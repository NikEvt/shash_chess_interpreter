import type { ShashinType } from '../types'

interface ShashinDesc {
  label: string
  short: string
  report: string
  prompt: string
}

const DESCRIPTIONS: Record<ShashinType, ShashinDesc> = {
  Tal: {
    label: 'Tactical / Attacking',
    short: 'sharp, tactical, attacking',
    report: 'Tactical / Attacking — sharp position with piece activity and threats. Look for combinations, sacrifices, and direct attacks on the king.',
    prompt: 'sharp tactical position — attacks, sacrifices, and king safety are key',
  },
  Capablanca: {
    label: 'Strategic / Balanced',
    short: 'balanced, strategic, positional',
    report: 'Strategic / Balanced — quiet positional play. Focus on piece improvement, weak squares, pawn structure, and long-term plans.',
    prompt: 'balanced strategic position — focus on piece coordination, weak squares, and long-term plans',
  },
  Petrosian: {
    label: 'Defensive / Solid',
    short: 'defensive, solid, prophylactic',
    report: 'Defensive / Solid — one side must hold a difficult position. Prophylaxis, exchanges, blockades, and neutralizing opponent\'s threats are the priority.',
    prompt: 'defensive position — prophylaxis, safe exchanges, and neutralizing threats are the priority',
  },
}

export function promptDescription(shashinType: ShashinType): string {
  return DESCRIPTIONS[shashinType]?.prompt ?? shashinType
}

export function reportDescription(shashinType: ShashinType): string {
  return DESCRIPTIONS[shashinType]?.report ?? shashinType
}

export function labelDescription(shashinType: ShashinType): string {
  return DESCRIPTIONS[shashinType]?.label ?? shashinType
}

export function getShashinType(scoreCp: number | null): ShashinType {
  if (scoreCp === null) return 'Tal'
  if (Math.abs(scoreCp) < 50) return 'Capablanca'
  if (Math.abs(scoreCp) > 150) return scoreCp > 0 ? 'Tal' : 'Petrosian'
  return 'Capablanca'
}
