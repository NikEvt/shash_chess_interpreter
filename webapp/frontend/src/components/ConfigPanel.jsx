import { useState } from 'react'

// Mirror of SECTION_FLAGS in prompt.py — (key, label, group)
const SECTION_FLAGS = [
  { key: 'include_system',                label: 'System instruction', group: 'core' },
  { key: 'include_last_move',             label: 'Last move',          group: 'core' },
  { key: 'include_eval_change',           label: 'Eval change',        group: 'core' },
  { key: 'include_engine_recommendation', label: 'Engine rec.',        group: 'core' },
  { key: 'include_pv_continuation',       label: 'PV continuation',    group: 'core' },
  { key: 'include_theory',                label: 'Theory',             group: 'core' },
  { key: 'include_game_phase',            label: 'Game phase',         group: 'alexander' },
  { key: 'include_score_table',           label: 'Score table',        group: 'alexander' },
  { key: 'include_pawn_structure',        label: 'Pawn structure',     group: 'alexander' },
  { key: 'include_space',                 label: 'Space',              group: 'alexander' },
  { key: 'include_mobility',             label: 'Mobility',           group: 'alexander' },
  { key: 'include_makogonov',             label: 'Makogonov',          group: 'alexander' },
]

// Default flags per preset — kept in sync with Python CONFIG_PRESETS
const PRESET_FLAGS = {
  minimal: {
    include_system: true,  include_last_move: true,  include_eval_change: true,
    include_engine_recommendation: true,  include_pv_continuation: false,
    include_theory: false,
    include_game_phase: false,  include_score_table: false,  include_pawn_structure: false,
    include_space: false,  include_mobility: false,  include_makogonov: false,
  },
  compact: {
    include_system: true,  include_last_move: true,  include_eval_change: true,
    include_engine_recommendation: true,  include_pv_continuation: true,
    include_theory: true,
    include_game_phase: true,  include_score_table: false,  include_pawn_structure: false,
    include_space: false,  include_mobility: false,  include_makogonov: false,
  },
  medium: {
    include_system: true,  include_last_move: true,  include_eval_change: true,
    include_engine_recommendation: true,  include_pv_continuation: true,
    include_theory: true,
    include_game_phase: true,  include_score_table: true,  include_pawn_structure: true,
    include_space: false,  include_mobility: true,  include_makogonov: false,
  },
  full: {
    include_system: true,  include_last_move: true,  include_eval_change: true,
    include_engine_recommendation: true,  include_pv_continuation: true,
    include_theory: true,
    include_game_phase: true,  include_score_table: true,  include_pawn_structure: true,
    include_space: true,  include_mobility: true,  include_makogonov: true,
  },
}

const PRESETS = ['minimal', 'compact', 'medium', 'full', 'custom']

export { PRESET_FLAGS, SECTION_FLAGS }

export default function ConfigPanel({
  configPreset, setConfigPreset,
  configFlags,  setConfigFlags,
  thinking,     setThinking,
  disabled,
}) {
  const [open, setOpen] = useState(false)

  // Effective flags: preset defaults merged with any custom overrides
  const effectiveFlags = configPreset === 'custom'
    ? { ...PRESET_FLAGS.full, ...configFlags }
    : { ...PRESET_FLAGS[configPreset] }

  function handlePresetClick(preset) {
    if (preset === 'custom') {
      // When switching to custom, seed from current preset flags
      const base = PRESET_FLAGS[configPreset] ?? PRESET_FLAGS.full
      setConfigFlags({ ...base })
    } else {
      setConfigFlags({})
    }
    setConfigPreset(preset)
  }

  function handleToggle(key) {
    const current = effectiveFlags[key] ?? true
    setConfigFlags(prev => ({ ...prev, [key]: !current }))
    if (configPreset !== 'custom') setConfigPreset('custom')
  }

  const coreFlags     = SECTION_FLAGS.filter(f => f.group === 'core')
  const alexanderFlags = SECTION_FLAGS.filter(f => f.group === 'alexander')

  const activeCount = Object.values(effectiveFlags).filter(Boolean).length

  return (
    <div className="config-panel">
      <button
        className="config-toggle"
        onClick={() => setOpen(o => !o)}
        disabled={disabled}
      >
        {open ? '▾' : '▸'} Prompt config
        <span className="config-preset-badge">{configPreset}</span>
        <span className="config-active-count">{activeCount}/{SECTION_FLAGS.length} sections</span>
        {thinking && <span className="config-thinking-badge">thinking ON</span>}
      </button>

      {open && (
        <div className="config-body">
          <div className="config-presets">
            {PRESETS.map(p => (
              <button
                key={p}
                className={`config-preset-btn ${configPreset === p ? 'active' : ''}`}
                onClick={() => handlePresetClick(p)}
                disabled={disabled}
              >
                {p}
              </button>
            ))}
          </div>

          <div className="config-flags-grid">
            <div className="config-group">
              <div className="config-group-label">LLM</div>
              <Toggle
                label="Thinking mode (/think)"
                checked={thinking}
                onChange={() => setThinking(v => !v)}
                disabled={disabled}
              />
            </div>

            <div className="config-group">
              <div className="config-group-label">Core</div>
              {coreFlags.map(({ key, label }) => (
                <Toggle
                  key={key}
                  label={label}
                  checked={effectiveFlags[key] ?? true}
                  onChange={() => handleToggle(key)}
                  disabled={disabled}
                />
              ))}
            </div>

            <div className="config-group">
              <div className="config-group-label">Alexander eval</div>
              {alexanderFlags.map(({ key, label }) => (
                <Toggle
                  key={key}
                  label={label}
                  checked={effectiveFlags[key] ?? false}
                  onChange={() => handleToggle(key)}
                  disabled={disabled}
                />
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Toggle({ label, checked, onChange, disabled }) {
  return (
    <label className={`config-toggle-row ${disabled ? 'disabled' : ''}`}>
      <span className={`config-switch ${checked ? 'on' : 'off'}`} onClick={disabled ? undefined : onChange} />
      <span className="config-toggle-label">{label}</span>
    </label>
  )
}
