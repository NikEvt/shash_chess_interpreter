#!/usr/bin/env bash
# Build Alexander engine for the current platform (macOS/Linux).
# Run from anywhere; output binary lands in Alexander/src/alexander.
#
# Usage:
#   bash alexander_interpreter/build_engine.sh          # auto-detect arch
#   bash alexander_interpreter/build_engine.sh --clean  # clean before build

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/Alexander/src"
JOBS="$(sysctl -n hw.logicalcpu 2>/dev/null || nproc 2>/dev/null || echo 4)"

if [[ ! -d "$SRC" ]]; then
    echo "ERROR: Alexander/src not found at $SRC" >&2
    exit 1
fi

# ── Detect arch ───────────────────────────────────────────────────────────────
KERNEL="$(uname -s)"
MACHINE="$(uname -m)"

case "$KERNEL-$MACHINE" in
    Darwin-arm64)
        ARCH="apple-silicon"
        COMP="clang"
        ;;
    Darwin-x86_64)
        ARCH="x86-64-avx2"
        COMP="clang"
        ;;
    Linux-aarch64|Linux-arm64)
        ARCH="armv8-dotprod"
        COMP="gcc"
        ;;
    Linux-x86_64)
        ARCH="x86-64-sse41-popcnt"
        COMP="gcc"
        ;;
    *)
        echo "Unrecognised platform $KERNEL-$MACHINE; falling back to generic 64-bit build." >&2
        ARCH="general-64"
        COMP="gcc"
        ;;
esac

echo "Platform : $KERNEL / $MACHINE"
echo "ARCH     : $ARCH"
echo "COMP     : $COMP"
echo "Jobs     : $JOBS"
echo

cd "$SRC"

# Strip x86-only flags that break ARM/Apple builds (same as Dockerfile)
if grep -q 'mprefer-vector-width\|mno-avx512f' Makefile 2>/dev/null; then
    echo "Patching Makefile: removing x86-only flags…"
    sed -i.bak 's/-mprefer-vector-width=256//g; s/-mno-avx512f//g' Makefile
fi

if [[ "${1:-}" == "--clean" ]]; then
    echo "Cleaning previous build…"
    make clean
fi

echo "Building…"
make -j"$JOBS" build ARCH="$ARCH" COMP="$COMP"

BINARY="$SRC/alexander"
if [[ ! -f "$BINARY" ]]; then
    echo "ERROR: build finished but binary not found at $BINARY" >&2
    exit 1
fi

echo
echo "Built → $BINARY  ($(du -sh "$BINARY" | cut -f1))"
echo
echo "To use with eval_game.py:"
echo "  python tests/eval_game.py --rerun-engine"
echo "  # or point to the binary explicitly:"
echo "  ALEXANDER_ENGINE_PATH=$BINARY python tests/eval_game.py --rerun-engine"
