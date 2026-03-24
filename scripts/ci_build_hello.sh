#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cmake --preset ap3p-gcc-ninja -S "$ROOT_DIR" -B "$ROOT_DIR/build/ap3p-gcc-ninja"
cmake --build --preset build-ap3p
