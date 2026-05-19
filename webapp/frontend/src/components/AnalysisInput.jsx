export default function AnalysisInput({
  pgnInput, onPgnChange,
  ourSide, onSideToggle,
  onAnalyze, analyzing,
}) {
  return (
    <div className="input-section">
      <textarea
        className="pgn-input"
        value={pgnInput}
        onChange={e => onPgnChange(e.target.value)}
        placeholder="Paste PGN or FEN here…"
        rows={4}
        disabled={analyzing}
      />
      <div className="input-controls">
        <button
          className="analyze-btn"
          onClick={onAnalyze}
          disabled={analyzing || !pgnInput.trim()}
        >
          {analyzing ? 'Analyzing…' : 'Analyze'}
        </button>
        <button
          className={`side-toggle ${ourSide}`}
          onClick={onSideToggle}
          disabled={analyzing}
          title="Toggle which side you are playing"
        >
          {ourSide === 'white' ? '⬜ Playing as White' : '⬛ Playing as Black'}
        </button>
      </div>
    </div>
  )
}
