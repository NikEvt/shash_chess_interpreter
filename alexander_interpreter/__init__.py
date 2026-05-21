"""
alexander_interpreter — chess analysis package using Alexander engine.

Drop-in replacement for the shash_chess_interpreter agent stack.
Key improvements over the ShashChess version:
  - 14-zone Shashin classification (accurate, from WDL)
  - MultiPV=3 top moves with per-move WDL
  - PV continuation in SAN
  - Optional eval trace (material, mobility, king safety, etc.)
  - Richer prompts that use all of the above

Public API:
    AlexanderResult    — core data type (types.py)
    AlexanderEngine    — subprocess engine wrapper (engine.py)
    build_prompt       — prompt builder for LLM (prompt.py)
    ask                — LLM client (llm.py)
    win_prob_to_shashin_zone — WDL → zone name (types.py)
"""

from .types import AlexanderResult, TopMove, EvalTrace, win_prob_to_shashin_zone
from .engine import AlexanderEngine
from .prompt import (
    build_prompt, build_prompt_sections,
    build_tiny_prompt, build_tiny_prompt_sections,
    PromptConfig,
    COMPACT_CONFIG, MEDIUM_CONFIG, FULL_CONFIG, MINIMAL_CONFIG,
    CONFIG_PRESETS, SECTION_FLAGS, build_config,
)
from .eval_parser import EvalSections, parse_eval_sections
from .llm import ask, LMStudioError, set_thinking, get_thinking
from .config import ENGINE_PATH, ENGINE_DEPTH, ENGINE_NUM_PV

__all__ = [
    "AlexanderResult",
    "TopMove",
    "EvalTrace",
    "win_prob_to_shashin_zone",
    "AlexanderEngine",
    "build_prompt",
    "build_prompt_sections",
    "build_tiny_prompt",
    "build_tiny_prompt_sections",
    "PromptConfig",
    "COMPACT_CONFIG",
    "MEDIUM_CONFIG",
    "FULL_CONFIG",
    "MINIMAL_CONFIG",
    "CONFIG_PRESETS",
    "SECTION_FLAGS",
    "build_config",
    "EvalSections",
    "parse_eval_sections",
    "ask",
    "LMStudioError",
    "set_thinking",
    "get_thinking",
    "ENGINE_PATH",
    "ENGINE_DEPTH",
    "ENGINE_NUM_PV",
]
