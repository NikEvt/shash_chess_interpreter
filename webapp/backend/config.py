import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from alexander_interpreter import ENGINE_DEPTH, ENGINE_NUM_PV  # noqa: E402

ENGINE_PATH = os.path.abspath(
    os.getenv(
        "ALEXANDER_ENGINE_PATH",
        os.path.join(REPO_ROOT, "Alexander/src/alexander"),
    )
)

ANALYSIS_DEPTH       = int(os.getenv("ANALYSIS_DEPTH",    str(ENGINE_DEPTH)))
NUM_PV               = int(os.getenv("ENGINE_NUM_PV",     str(ENGINE_NUM_PV)))
ENGINE_THREADS       = int(os.getenv("ENGINE_THREADS",    "8"))
ENGINE_HASH_MB       = int(os.getenv("ENGINE_HASH_MB",    "256"))
ENGINE_TIMEOUT       = int(os.getenv("ENGINE_TIMEOUT",    "60"))

STATIC_DIR           = os.getenv("STATIC_DIR", "")

COMMENTARY_CONCURRENCY = 3
MAX_TOKENS             = 350
