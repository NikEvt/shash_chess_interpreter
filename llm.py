"""
LM Studio client — OpenAI-compatible REST API.
Synchronous (no asyncio) for simplicity in standalone agent usage.
"""
import re
import httpx
from config import LM_STUDIO_URL, MODEL_NAME, MAX_LLM_TOKENS

# qwen3 thinking-mode output: <think>...</think> before the actual answer
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text: str) -> str:
    """Remove qwen3 chain-of-thought blocks, return only the final answer."""
    return _THINK_RE.sub("", text).strip()


class LMStudioError(Exception):
    pass


def ask(prompt: str, temperature: float = 0.4) -> str:
    url = f"{LM_STUDIO_URL}/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": MAX_LLM_TOKENS,
        "temperature": temperature,
        "stream": False,
    }
    try:
        resp = httpx.post(url, json=payload, timeout=30.0)
        resp.raise_for_status()
    except httpx.ConnectError as e:
        raise LMStudioError(
            f"Cannot connect to LM Studio at {LM_STUDIO_URL}. "
            "Make sure it is running and the server is started."
        ) from e
    except httpx.HTTPStatusError as e:
        raise LMStudioError(f"LM Studio returned {e.response.status_code}: {e.response.text}") from e

    data = resp.json()
    try:
        raw = data["choices"][0]["message"]["content"]
        return _strip_think(raw)
    except (KeyError, IndexError) as e:
        raise LMStudioError(f"Unexpected response format: {data}") from e
