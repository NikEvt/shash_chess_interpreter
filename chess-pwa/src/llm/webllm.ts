import { CreateMLCEngine } from '@mlc-ai/web-llm'
import type { MLCEngine } from '@mlc-ai/web-llm'

// Qwen3-0.6B quantized — ~400 MB, cached in IndexedDB after first download
const MODEL_ID = 'Qwen3-0.6B-q4f16_1-MLC'

type LoadProgress = { progress: number; text: string }

let enginePromise: Promise<MLCEngine> | null = null

export function loadLLM(onProgress: (p: LoadProgress) => void): Promise<MLCEngine> {
  if (!enginePromise) {
    enginePromise = CreateMLCEngine(MODEL_ID, {
      initProgressCallback: ({ progress, text }) => onProgress({ progress, text }),
    })
  }
  return enginePromise
}

export async function askLLM(
  engine: MLCEngine,
  prompt: string,
  onToken: (delta: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  let full = ''

  // Strip <think>...</think> chain-of-thought blocks from Qwen3
  const stripThink = (text: string) =>
    text.replace(/<think>[\s\S]*?<\/think>/g, '').trim()

  const stream = await engine.chat.completions.create({
    messages: [{ role: 'user', content: prompt }],
    max_tokens: 400,
    temperature: 0.4,
    stream: true,
  })

  for await (const chunk of stream) {
    if (signal?.aborted) break
    const delta = chunk.choices[0]?.delta?.content ?? ''
    if (delta) {
      full += delta
      // Stream cleaned text — skip tokens inside <think> blocks
      const cleaned = stripThink(full)
      if (cleaned.length > 0) onToken(cleaned)
    }
  }

  return stripThink(full)
}
