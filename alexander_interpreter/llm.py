"""LM Studio client (OpenAI-compatible). Same as the original llm.py."""
import re
import httpx
from .config import LM_STUDIO_URL, MODEL_NAME, MAX_LLM_TOKENS


def _strip_think(text: str) -> str:
    """Remove <think>...</think> blocks including unclosed ones."""
    # Remove properly closed blocks
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL)
    # Remove any leftover unclosed <think> tag and everything after it
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    return text.strip()


class LMStudioError(Exception):
    pass


def _call_lm(prompt: str, temperature: float, max_tokens: int) -> tuple[str, str | None]:
    """
    Make a single request to LM Studio.
    Returns (content, finish_reason). finish_reason can be "stop", "length", or None.
    """
    url = f"{LM_STUDIO_URL}/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    resp = httpx.post(url, json=payload, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
        finish_reason = data["choices"][0].get("finish_reason")
        return content, finish_reason
    except (KeyError, IndexError) as e:
        raise LMStudioError(f"Unexpected response format: {data}") from e


def ask(prompt: str, temperature: float = 0.4, max_tokens: int | None = None) -> str:
    """
    Send prompt to LM Studio. If the response is truncated due to token limit,
    retry with a modified prompt that discourages thinking tags.
    """
    max_tokens_actual = max_tokens if max_tokens is not None else MAX_LLM_TOKENS

    try:
        # First attempt with original prompt
        content, finish_reason = _call_lm(prompt, temperature, max_tokens_actual)
        
        # If finished normally (or other reason), just clean and return
        if finish_reason != "length":
            return _strip_think(content)
        
        
        suppressed_prompt = (
            f"\no_think\n\n{prompt}\n\n"
        )
        
        # Optionally increase max_tokens slightly to ensure completion
        retry_max_tokens = max(max_tokens_actual, 512)  # at least 512 tokens for the answer
        
        content2, finish_reason2 = _call_lm(suppressed_prompt, temperature, retry_max_tokens)
        
        # Even if this also truncates, at least we strip any partial think
        return _strip_think(content2)
        
    except httpx.ConnectError as e:
        raise LMStudioError(
            f"Cannot connect to LM Studio at {LM_STUDIO_URL}. "
            "Make sure it is running and the server is started."
        ) from e
    except httpx.HTTPStatusError as e:
        raise LMStudioError(f"LM Studio returned {e.response.status_code}: {e.response.text}") from e