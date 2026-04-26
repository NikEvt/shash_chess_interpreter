#!/usr/bin/env bash
# Build ShashChess → WebAssembly (shashchess.js + shashchess.wasm)
# Output: chess-pwa/public/engine/shashchess.{js,wasm}
#
# Requires Emscripten SDK:
#   git clone https://github.com/emscripten-core/emsdk ~/emsdk
#   cd ~/emsdk && ./emsdk install latest && ./emsdk activate latest
#   source ~/emsdk/emsdk_env.sh
#
# Notes:
#   -DNNUE_EMBEDDING_OFF  — отключает inline x86 asm; NNUE грузится из Emscripten VFS.
#   -pthread              — нужен потому что ShashChess создаёт std::thread (ThreadPool).
#                           Без него emcc абортирует при pthread_create.
#   PTHREAD_POOL_SIZE=4   — pre-spawns 4 worker threads в пуле.
#   (без USE_LIVEBOOK)    — livebook защищён #ifdef USE_LIVEBOOK, libcurl не нужен.
#
# Usage:
#   cd chess-pwa && bash scripts/build-wasm.sh

set -e

# Source emsdk if emcc not yet in PATH
if ! command -v emcc &>/dev/null; then
  EMSDK_ENV="${HOME}/emsdk/emsdk_env.sh"
  if [ -f "$EMSDK_ENV" ]; then
    # shellcheck disable=SC1090
    source "$EMSDK_ENV" 2>/dev/null || true
  fi
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$SCRIPT_DIR/.."
SRC_DIR="/Users/ivanivanov/Documents/chess_report/ShashChess/src"
OUT_DIR="$REPO_ROOT/public/engine"

if ! command -v emcc &>/dev/null; then
  echo "ERROR: emcc not found. Install Emscripten SDK and source emsdk_env.sh"
  exit 1
fi

emcc --version
mkdir -p "$OUT_DIR"

SRCS=(
  benchmark.cpp bitboard.cpp evaluate.cpp main.cpp
  misc.cpp movegen.cpp movepick.cpp position.cpp
  search.cpp thread.cpp timeman.cpp tt.cpp uci.cpp ucioption.cpp tune.cpp
  syzygy/tbprobe.cpp
  learn/learn.cpp
  mcts/montecarlo.cpp
  book/file_mapping.cpp book/book.cpp book/book_manager.cpp
  book/polyglot/polyglot.cpp book/ctg/ctg.cpp
  nnue/nnue_accumulator.cpp nnue/nnue_misc.cpp nnue/network.cpp
  nnue/features/half_ka_v2_hm.cpp nnue/features/full_threats.cpp
  engine.cpp score.cpp memory.cpp
  wdl/win_probability.cpp
  livebook/BaseLivebook.cpp livebook/LichessOpening.cpp livebook/LichessEndgame.cpp
  livebook/ChessDb.cpp livebook/LichessLivebook.cpp livebook/LichessMaster.cpp
  livebook/LichessPlayer.cpp livebook/LichessUsers.cpp livebook/LichessGames.cpp
  livebook/Proxy.cpp livebook/ChessDBContributor.cpp
  livebook/analysis/Cp.cpp livebook/analysis/Analysis.cpp
  livebook/analysis/Wdl.cpp livebook/analysis/Mate.cpp
  shashin/shashin_manager.cpp shashin/moveconfig.cpp
)

NNUE_BIG="nn-c288c895ea92.nnue"
NNUE_SMALL="nn-37f18f62d772.nnue"

INCLUDE_FLAGS=(
  -I. -Ishashin -Ilearn
  -Innue -Innue/features -Innue/layers
  -Ibook -Ibook/polyglot -Ibook/ctg
  -Imcts -Isyzygy
  -Ilivebook -Ilivebook/analysis -Ilivebook/json
  -Iwdl
)

# -pthread: required — ShashChess creates std::thread (ThreadPool); without it emcc aborts
COMPILE_FLAGS=(
  -O2 -std=c++17 -DNDEBUG -DIS_64BIT -DUSE_POPCNT -DNNUE_EMBEDDING_OFF -fno-exceptions
  -pthread
  "${INCLUDE_FLAGS[@]}"
)

echo "==> Compiling ShashChess WASM with pthreads (this may take 5-10 minutes)…"
cd "$SRC_DIR"

OBJ_FILES=()
for src in "${SRCS[@]}"; do
  obj="$OUT_DIR/$(basename "${src%.cpp}").o"
  echo "  cc $src"
  emcc "${COMPILE_FLAGS[@]}" -c "$src" -o "$obj"
  OBJ_FILES+=("$obj")
done

echo "==> Linking…"
emcc -O2 \
  "${OBJ_FILES[@]}" \
  -sENVIRONMENT=worker \
  -sMODULARIZE=1 \
  -sEXPORT_NAME=ShashChess \
  -sALLOW_MEMORY_GROWTH=1 \
  -sINITIAL_MEMORY=134217728 \
  -sSTACK_SIZE=2097152 \
  "-sEXPORTED_FUNCTIONS=[\"_main\"]" \
  "-sEXPORTED_RUNTIME_METHODS=[\"callMain\"]" \
  -sFORCE_FILESYSTEM=1 \
  -pthread \
  -sPTHREAD_POOL_SIZE=4 \
  "--embed-file=${NNUE_BIG}@/${NNUE_BIG}" \
  "--embed-file=${NNUE_SMALL}@/${NNUE_SMALL}" \
  -o "$OUT_DIR/shashchess.js"

rm -f "$OUT_DIR"/*.o

echo ""
echo "✓ Build complete!"
ls -lh "$OUT_DIR/shashchess"*
echo ""
echo "==> Run: cd chess-pwa && npm run dev"
