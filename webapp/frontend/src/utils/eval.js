/**
 * Convert centipawn score / mate-in to a White-win percentage [0..100].
 * Uses an arctan curve so ±400cp ≈ ±50 pp from 50%.
 */
export function evalToPercent(cp, mate) {
  if (mate !== null && mate !== undefined) return mate > 0 ? 100 : 0
  if (cp  === null || cp  === undefined)   return 50
  return 50 + 50 * (2 / Math.PI) * Math.atan(cp / 400)
}

/**
 * Format eval as a display string.
 * @param {number|null} cp   - centipawns (White perspective)
 * @param {number|null} mate - mate-in N (positive = White mates)
 * @param {boolean} [short]  - use one decimal place instead of two
 * @returns {{ text: string, cls: 'positive'|'negative'|'equal' }}
 */
export function formatEval(cp, mate, short = false) {
  if (mate !== null && mate !== undefined) {
    return {
      text: mate > 0 ? `+M${Math.abs(mate)}` : `-M${Math.abs(mate)}`,
      cls:  mate > 0 ? 'positive' : 'negative',
    }
  }
  if (cp === null || cp === undefined) {
    return { text: '–', cls: 'equal' }
  }
  const v = cp / 100
  return {
    text: (v >= 0 ? '+' : '') + v.toFixed(short ? 1 : 2),
    cls:  v > 0.1 ? 'positive' : v < -0.1 ? 'negative' : 'equal',
  }
}
