#!/usr/bin/env bash
# Create, build, flash, and view an NSX hello-world app for atomiq110 in one go.
#
# Usage:
#   scripts/hello_atomiq110.sh [app_dir] [--board BOARD] [--no-view] [--force]
#
#   app_dir   Where to create the app (default: generated_examples/my_hello).
#   --board   Target board (default: atomiq110_fpga_turbo).
#   --no-view Skip the SWO viewer at the end (flash only).
#   --force   Recreate the app even if app_dir already exists.
#
# Requires a connected SEGGER J-Link probe for the flash/view steps.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

APP_DIR="$ROOT_DIR/generated_examples/my_hello"
BOARD="atomiq110_fpga_turbo"
VIEW=1
FORCE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --board)   BOARD="$2"; shift 2 ;;
        --no-view) VIEW=0; shift ;;
        --force)   FORCE=1; shift ;;
        -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
        -*)        echo "unknown option: $1" >&2; exit 2 ;;
        *)         APP_DIR="$1"; shift ;;
    esac
done

nsx() { uv run --project "$ROOT_DIR" -q nsx "$@"; }

echo "==> nsx doctor"
nsx doctor

if [[ -d "$APP_DIR" && $FORCE -eq 0 ]]; then
    echo "==> $APP_DIR already exists; reusing (pass --force to recreate)"
else
    rm -rf "$APP_DIR"
    echo "==> creating app at $APP_DIR (board: $BOARD)"
    nsx create-app "$APP_DIR" --board "$BOARD"
fi

echo "==> configure"
nsx configure --app-dir "$APP_DIR"

echo "==> build"
nsx build --app-dir "$APP_DIR"

echo "==> flash"
nsx flash --app-dir "$APP_DIR"

if [[ $VIEW -eq 1 ]]; then
    echo "==> opening SWO viewer (Ctrl-C to exit)"
    nsx view --app-dir "$APP_DIR"
else
    echo "==> done (skipped viewer). To watch output later:"
    echo "    uv run nsx view --app-dir $APP_DIR"
fi
