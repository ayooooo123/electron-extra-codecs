#!/usr/bin/env bash
#
# Patch FFmpeg for extra codec support (HEVC, AC3, EAC3, DTS).
#
# Step 1: Patches build_ffmpeg.py Chrome branding flags (for manual regen on Ubuntu)
# Step 2: Directly patches pre-generated config files via patch_ffmpeg_configs.py
#
# This avoids running build_ffmpeg.py (which requires Ubuntu/Debian) by
# directly modifying the config headers, codec lists, and GN includes.
#
# Must be run from the Chromium src/ directory.
#
# Usage:
#   bash patch_ffmpeg.sh [ffmpeg-dir]          # apply patches
#   bash patch_ffmpeg.sh --check [ffmpeg-dir]  # dry-run / validate only

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--check" || "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  shift
fi

FFMPEG_DIR="${1:-third_party/ffmpeg}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_FFMPEG_PY="media/ffmpeg/scripts/build_ffmpeg.py"

if [[ ! -d "$FFMPEG_DIR" ]]; then
  echo "ERROR: FFmpeg dir not found: $FFMPEG_DIR" >&2
  exit 1
fi

if [[ ! -f "$BUILD_FFMPEG_PY" ]]; then
  echo "ERROR: build_ffmpeg.py not found: $BUILD_FFMPEG_PY" >&2
  exit 1
fi

for tool in python3 bash; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: Missing required tool: $tool" >&2
    exit 1
  fi
done

DRY_RUN_FLAG=""
if $DRY_RUN; then
  DRY_RUN_FLAG="--check"
fi

echo "Step 1: Patching build_ffmpeg.py Chrome branding flags"
python3 - "$BUILD_FFMPEG_PY" $DRY_RUN_FLAG <<'PY'
import re
import shutil
import sys
from pathlib import Path

dry_run = "--check" in sys.argv
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
orig = text

adds = {
    "decoder": ["eac3", "ac3", "hevc", "mpeg4", "mpegvideo", "mp2", "mp1", "flac", "dca"],
    "demuxer": ["dtshd", "dts", "avi", "mpegvideo", "m4v", "h264", "vc1", "flac", "hevc"],
    "parser": ["mpeg4video", "mpegvideo", "ac3", "h261", "vc1", "h263", "flac", "hevc", "dca"],
}

def patch_flag(kind: str, src: str) -> tuple[str, int]:
    pat = re.compile(rf"(--enable-{kind}=)([a-z0-9_,\-]+)")
    hits = 0

    def repl(m):
        nonlocal hits
        existing = [x for x in m.group(2).split(",") if x]
        seen = set(existing)
        for item in adds[kind]:
            if item not in seen:
                existing.append(item)
                seen.add(item)
        hits += 1
        return m.group(1) + ",".join(existing)

    out = pat.sub(repl, src)
    return out, hits

chrome_markers = [
    "configure_flags['Chrome']",
    'configure_flags["Chrome"]',
]
found_marker = None
for marker in chrome_markers:
    if marker in text:
        found_marker = marker
        break
if found_marker is None:
    raise SystemExit("ERROR: configure_flags['Chrome'] section not found")

start = text.index(found_marker)
tail = text[start:]

for k in ("decoder", "demuxer", "parser"):
    patched, hits = patch_flag(k, tail)
    if hits == 0:
        raise SystemExit(f"ERROR: --enable-{k}=... line not found in Chrome section")
    tail = patched

text = text[:start] + tail

if text == orig:
    print("build_ffmpeg.py already contains requested codec flags")
    sys.exit(0)

if dry_run:
    print("Dry run: build_ffmpeg.py patches validated")
    sys.exit(0)

backup = path.with_suffix(path.suffix + ".orig")
if not backup.exists():
    shutil.copy2(path, backup)

path.write_text(text, encoding="utf-8")
print("Patched build_ffmpeg.py flags for Chrome branding")
PY

echo "Step 2: Patching pre-generated FFmpeg config files and GN includes"
python3 "$SCRIPT_DIR/patch_ffmpeg_configs.py" $DRY_RUN_FLAG

echo "FFmpeg patching complete"
