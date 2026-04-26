/// <reference lib="webworker" />
// ShashChess WASM Web Worker
//
// The engine runs its UCI loop in main() which blocks on getchar().
// We use SharedArrayBuffer + Atomics.wait for a truly blocking stdin so
// the engine never sees EOF. Main thread writes commands directly to the
// SAB (no postMessage — worker event loop is frozen while WASM blocks).

const SAB_SIZE = 16384
const inputSAB = new SharedArrayBuffer(SAB_SIZE + 8)
const sabAvail = new Int32Array(inputSAB, 0, 1)   // [0] = bytes available
const sabData  = new Uint8Array(inputSAB, 8)       // circular char buffer
let readPos = 0

// Post SAB to main thread BEFORE engine starts so main can write commands
self.postMessage({ type: 'sab', sab: inputSAB })

let stdinCallCount = 0
let stdinAccum = ''  // accumulate chars, flush on newline or every 60 chars

function stdinFn(): number {
  stdinCallCount++

  // Block until a byte is available
  while (Atomics.load(sabAvail, 0) === 0) {
    // Flush accumulated chars before blocking so we see what was read so far
    if (stdinAccum) {
      self.postMessage({ type: 'debug', data: `stdin read: "${stdinAccum}" | blocking #${stdinCallCount}` })
      stdinAccum = ''
    } else {
      self.postMessage({ type: 'debug', data: `stdin blocking #${stdinCallCount} av=0` })
    }
    let waitResult: string
    try {
      waitResult = Atomics.wait(sabAvail, 0, 0, 30000) // 30s timeout
    } catch (e) {
      self.postMessage({ type: 'error', data: `Atomics.wait threw: ${e}` })
      return -1
    }
    if (waitResult === 'timed-out') {
      self.postMessage({ type: 'debug', data: `stdin TIMEOUT at #${stdinCallCount}` })
    }
  }

  const ch = sabData[readPos % SAB_SIZE]
  readPos++
  Atomics.sub(sabAvail, 0, 1)

  // Accumulate for display; flush on newline or when long enough
  stdinAccum += ch === 10 ? '\\n' : ch < 32 ? `\\x${ch.toString(16).padStart(2,'0')}` : String.fromCharCode(ch)
  if (ch === 10 || stdinAccum.length >= 60) {
    self.postMessage({ type: 'debug', data: `stdin read: "${stdinAccum}"` })
    stdinAccum = ''
  }

  return ch
}

async function init() {
  try {
    const res = await fetch('/engine/shashchess.js')
    if (!res.ok) throw new Error(`HTTP ${res.status} fetching /engine/shashchess.js`)
    const src = await res.text()

    // eslint-disable-next-line no-new-func
    const factory = new Function(src + '\nreturn ShashChess;')() as (m: object) => Promise<void>

    await factory({
      locateFile(path: string) { return '/engine/' + path },
      // pthread sub-workers load this URL; shashchess.js ends with
      // `isPthread && ShashChess()` so they self-initialize correctly
      mainScriptUrlOrBlob: '/engine/shashchess.js',
      // TTY-based stdout — calls print() on each complete line
      print(line: string) {
        self.postMessage({ type: 'stdout', data: line })
        // Mirror to debug channel so debugLines panel shows stdout too
        self.postMessage({ type: 'debug', data: `OUT: ${line}` })
      },
      printErr(line: string) {
        if (line && line.trim()) {
          self.postMessage({ type: 'debug', data: `ERR: ${line}` })
        }
      },
      stdin: stdinFn,
      onRuntimeInitialized() {
        self.postMessage({ type: 'engine_init' })
      },
      onAbort(what: unknown) {
        self.postMessage({ type: 'error', data: `Engine aborted: ${what}` })
      },
    })
  } catch (err) {
    self.postMessage({ type: 'error', data: `Engine load failed: ${err}` })
  }
}

init()
