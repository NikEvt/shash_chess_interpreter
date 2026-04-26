interface Props {
  text: string
  progress: number // 0..1
}

export default function LoadProgress({ text, progress }: Props) {
  const pct = Math.round(progress * 100)
  return (
    <div className="load-progress-overlay">
      <div className="load-progress-box">
        <div className="load-progress-title">Loading AI Model</div>
        <div className="load-progress-sub">{text || 'Initializing…'}</div>
        <div className="load-progress-bar-track">
          <div className="load-progress-bar-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="load-progress-pct">{pct}%</div>
        <div className="load-progress-note">
          First load downloads ~400 MB (Qwen3-0.6B). Cached locally after that.
        </div>
      </div>
    </div>
  )
}
