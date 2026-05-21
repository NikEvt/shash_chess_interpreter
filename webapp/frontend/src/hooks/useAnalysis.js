import { useState, useCallback, useRef } from 'react'

/**
 * Manages the full analysis lifecycle:
 *  - form state (pgn input, side)
 *  - SSE stream reading
 *  - positions array updates
 *  - phase / progress tracking
 */
export function useAnalysis() {
  const [pgnInput,            setPgnInput]            = useState('')
  const [positions,           setPositions]           = useState([])
  const [currentIdx,          setCurrentIdx]          = useState(0)
  const [analyzing,           setAnalyzing]           = useState(false)
  const [error,               setError]               = useState(null)
  const [total,               setTotal]               = useState(0)
  const [engineProgress,      setEngineProgress]      = useState(0)
  const [commentaryProgress,  setCommentaryProgress]  = useState(0)
  const [phase,               setPhase]               = useState('idle') // idle|engine|commentary|done
  const [ourSide,             setOurSide]             = useState('white')
  const [configPreset,        setConfigPreset]        = useState('full')
  const [configFlags,         setConfigFlags]         = useState({})
  const [thinking,            setThinking]            = useState(false)

  const readerRef = useRef(null)

  // ── SSE message dispatcher ─────────────────────────────────────────────────

  const handleMessage = useCallback((data) => {
    switch (data.type) {
      case 'start':
        setTotal(data.total)
        setPhase('engine')
        break

      case 'engine':
        setPositions(prev => {
          const next = [...prev]
          while (next.length <= data.index) next.push(null)
          next[data.index] = data.position
          return next
        })
        setEngineProgress(data.index + 1)
        break

      case 'commentary_start':
        setPhase('commentary')
        setCommentaryProgress(0)
        break

      case 'commentary':
        setPositions(prev => {
          const next = [...prev]
          if (next[data.index]) {
            next[data.index] = {
              ...next[data.index],
              commentary:      data.commentary,
              prompt_sections: data.prompt_sections ?? null,
              full_prompt:     data.full_prompt     ?? null,
              config_preset:   data.config_preset   ?? null,
            }
          }
          return next
        })
        setCommentaryProgress(p => p + 1)
        break

      case 'complete':
        setPhase('done')
        setAnalyzing(false)
        break

      case 'error':
        setError(data.message)
        setAnalyzing(false)
        setPhase('idle')
        break
    }
  }, [])

  // ── Stream reader ──────────────────────────────────────────────────────────

  const analyze = useCallback(async () => {
    if (!pgnInput.trim()) return

    setAnalyzing(true)
    setError(null)
    setPositions([])
    setCurrentIdx(0)
    setTotal(0)
    setEngineProgress(0)
    setCommentaryProgress(0)
    setPhase('idle')

    try {
      const response = await fetch('/api/analyze', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({
          pgn:           pgnInput,
          our_side:      ourSide,
          config_preset: configPreset,
          config_flags:  configFlags,
          thinking:      thinking,
        }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)

      const reader  = response.body.getReader()
      readerRef.current = reader
      const decoder = new TextDecoder()
      let buffer    = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() ?? ''

        for (const chunk of chunks) {
          const line = chunk.split('\n').find(l => l.startsWith('data: '))
          if (!line) continue
          try { handleMessage(JSON.parse(line.slice(6))) } catch { /* malformed line */ }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') setError(err.message)
    } finally {
      setAnalyzing(false)
    }
  }, [pgnInput, ourSide, configPreset, configFlags, thinking, handleMessage])

  return {
    // form
    pgnInput, setPgnInput,
    ourSide,  setOurSide,
    // config
    configPreset, setConfigPreset,
    configFlags,  setConfigFlags,
    thinking,     setThinking,
    // trigger
    analyze,
    // analysis data
    positions, setPositions,
    currentIdx, setCurrentIdx,
    // status
    analyzing,
    error,
    total,
    engineProgress,
    commentaryProgress,
    phase,
  }
}
