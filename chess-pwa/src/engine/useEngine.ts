import { useRef, useCallback, useEffect, useState } from 'react'
import { parseInfoLine, parseBestMove, buildEngineResult } from './uciParser'
import type { EngineResult } from '../types'

type EngineState = 'unavailable' | 'loading' | 'ready' | 'analyzing'

const SAB_SIZE = 16384

export function useEngine() {
  const workerRef    = useRef<Worker | null>(null)
  const sabAvailRef  = useRef<Int32Array | null>(null)
  const sabDataRef   = useRef<Uint8Array | null>(null)
  const sabWritePos  = useRef(0)

  const [engineState, setEngineState] = useState<EngineState>('loading')
  const [engineError, setEngineError] = useState<string | null>(null)
  const [engineLog, setEngineLog] = useState<string>('waiting for WASM…')
  const [debugLines, setDebugLines] = useState<string[]>([])

  const resolveRef      = useRef<((r: EngineResult) => void) | null>(null)
  const rejectRef       = useRef<((e: Error) => void) | null>(null)
  const pendingFenRef   = useRef<string>('')
  const bestInfoRef     = useRef<Partial<EngineResult>>({})
  const rawLinesRef     = useRef<string[]>([])

  // Write a UCI command line directly into the SharedArrayBuffer.
  // The worker is blocked in Atomics.wait (inside main()), so postMessage
  // is not used — SAB write + notify is the only way to reach it.
  const sendCmd = useCallback((line: string) => {
    const avail = sabAvailRef.current
    const data  = sabDataRef.current
    if (!avail || !data) return
    const bytes = new TextEncoder().encode(line + '\n')
    for (const b of bytes) {
      data[sabWritePos.current % SAB_SIZE] = b
      sabWritePos.current++
    }
    Atomics.add(avail, 0, bytes.length)
    Atomics.notify(avail, 0, 1) // wake the blocked worker
  }, [])

  useEffect(() => {
    const worker = new Worker(new URL('./engineWorker.ts', import.meta.url), { type: 'module' })

    worker.onmessage = (e: MessageEvent) => {
      const msg = e.data as { type: string; data?: string; sab?: SharedArrayBuffer }

      // Step 1: worker sends SAB before WASM starts — wire it up
      if (msg.type === 'sab' && msg.sab) {
        sabAvailRef.current = new Int32Array(msg.sab, 0, 1)
        sabDataRef.current  = new Uint8Array(msg.sab, 8)
        sabWritePos.current = 0
        // Send initial UCI handshake into the SAB
        sendCmd('uci')
        sendCmd('isready')
        return
      }

      if (msg.type === 'engine_init') {
        setEngineLog('runtime init — waiting for readyok…')
        return
      }

      if (msg.type === 'debug') {
        const line = msg.data ?? ''
        setEngineLog(`DBG: ${line}`)
        setDebugLines(prev => [...prev.slice(-19), line])
        return
      }

      if (msg.type === 'error') {
        const line = msg.data ?? 'unknown error'
        console.warn('ShashChess engine unavailable:', line)
        setDebugLines(prev => [...prev.slice(-19), `ERROR: ${line}`])
        setEngineError(line)
        setEngineState('unavailable')
        return
      }

      if (msg.type === 'stdout' && msg.data) {
        const line = msg.data
        setEngineLog(line.slice(0, 80))

        // 'readyok' = engine finished processing 'isready' → truly ready
        if (line.trim() === 'readyok') {
          setEngineState('ready')
          return
        }

        if (line.startsWith('info') && line.includes('depth')) {
          rawLinesRef.current.push(line)
          const parsed = parseInfoLine(line, pendingFenRef.current)
          if (parsed) Object.assign(bestInfoRef.current, parsed)
        }

        if (line.startsWith('bestmove') && resolveRef.current) {
          rawLinesRef.current.push(line)
          const bestMoveUci = parseBestMove(line)
          if (bestMoveUci && bestMoveUci !== '(none)') {
            const info = bestInfoRef.current
            const result = buildEngineResult({
              fen:        pendingFenRef.current,
              bestMoveUci,
              scoreCp:    info.scoreCp ?? null,
              mateIn:     info.mateIn  ?? null,
              wdlWin:     info.wdlWin  ?? 500,
              wdlDraw:    info.wdlDraw ?? 0,
              wdlLoss:    info.wdlLoss ?? 500,
              depth:      info.depth   ?? 1,
              pvUci:      info.pvUci   ?? [],
            })
            result.rawLines = [...rawLinesRef.current]
            resolveRef.current(result)
          } else {
            rejectRef.current?.(new Error('No bestmove returned'))
          }
          resolveRef.current = null
          rejectRef.current  = null
          bestInfoRef.current = {}
          rawLinesRef.current = []
          setEngineState('ready')
        }
      }
    }

    worker.onerror = (e) => {
      console.warn('Engine worker error:', e.message)
      setEngineError(e.message ?? 'worker onerror')
      setEngineState('unavailable')
    }

    workerRef.current = worker
    return () => worker.terminate()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const analyze = useCallback((fen: string, depth = 15): Promise<EngineResult> => {
    return new Promise((resolve, reject) => {
      if (!workerRef.current || engineState === 'unavailable') {
        reject(new Error('Engine not available'))
        return
      }
      if (!sabAvailRef.current) {
        reject(new Error('Engine SAB not ready'))
        return
      }
      setEngineState('analyzing')
      pendingFenRef.current  = fen
      bestInfoRef.current    = {}
      rawLinesRef.current    = []
      resolveRef.current     = resolve
      rejectRef.current      = reject

      sendCmd('stop')
      sendCmd(`position fen ${fen}`)
      sendCmd(`go depth ${depth}`)
    })
  }, [engineState, sendCmd])

  return { analyze, engineState, engineError, engineLog, debugLines }
}
