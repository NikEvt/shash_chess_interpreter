import os

# Path to compiled Alexander binary
ENGINE_PATH = os.getenv(
    "ALEXANDER_ENGINE_PATH",
    os.path.join(os.path.dirname(__file__), "../../Alexander/src/alexander"),
)

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "qwen3-0.6b")
MAX_LLM_TOKENS = int(os.getenv("MAX_LLM_TOKENS", "600"))

ENGINE_DEPTH = int(os.getenv("ENGINE_DEPTH", "15"))
ENGINE_NUM_PV = int(os.getenv("ENGINE_NUM_PV", "3"))
ENGINE_THREADS = int(os.getenv("ENGINE_THREADS", "8"))
ENGINE_HASH_MB = int(os.getenv("ENGINE_HASH_MB", "256"))
ENGINE_TIMEOUT = float(os.getenv("ENGINE_TIMEOUT", "30.0"))
