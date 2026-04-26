// Lightweight BM25Okapi — no external deps, fast enough for 28 docs
const K1 = 1.5
const B = 0.75

function tokenize(text: string): string[] {
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').split(/\s+/).filter(Boolean)
}

export class BM25 {
  private docs: string[][]
  private idf: Map<string, number>
  private avgdl: number

  constructor(documents: string[]) {
    this.docs = documents.map(tokenize)
    this.avgdl = this.docs.reduce((s, d) => s + d.length, 0) / (this.docs.length || 1)
    this.idf = this._buildIdf()
  }

  private _buildIdf(): Map<string, number> {
    const df = new Map<string, number>()
    for (const doc of this.docs) {
      const seen = new Set(doc)
      for (const t of seen) df.set(t, (df.get(t) ?? 0) + 1)
    }
    const N = this.docs.length
    const idf = new Map<string, number>()
    for (const [t, n] of df) {
      idf.set(t, Math.log((N - n + 0.5) / (n + 0.5) + 1))
    }
    return idf
  }

  getScores(query: string | string[]): number[] {
    const tokens = typeof query === 'string' ? tokenize(query) : query
    return this.docs.map((doc) => {
      const tf = new Map<string, number>()
      for (const t of doc) tf.set(t, (tf.get(t) ?? 0) + 1)
      const dl = doc.length
      return tokens.reduce((score, term) => {
        const f = tf.get(term) ?? 0
        if (f === 0) return score
        const idf = this.idf.get(term) ?? 0
        return score + idf * (f * (K1 + 1)) / (f + K1 * (1 - B + B * dl / this.avgdl))
      }, 0)
    })
  }
}
