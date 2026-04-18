import os

ENGINE_PATH = os.getenv("ENGINE_PATH", "../ShashChess/src/ShashChess")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "loaded-model")
ENGINE_DEPTH = int(os.getenv("ENGINE_DEPTH", "15"))
MAX_LLM_TOKENS = int(os.getenv("MAX_LLM_TOKENS", "400"))
ENGINE_TIMEOUT = float(os.getenv("ENGINE_TIMEOUT", "10.0"))
