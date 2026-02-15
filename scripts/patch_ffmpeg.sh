#!/usr/bin/env bash
#
# Patch build_ffmpeg.py to add extra codec flags to the Chrome branding, then
# regenerate ffmpeg configs for all targets.
#
# In Chromium 144+ the build/generate scripts live in media/ffmpeg/scripts/
# while copy_config.sh remains in third_party/ffmpeg/chromium/scripts/.
#
# Must be run from the Chromium src/ directory.
#
# Usage:
#   bash patch_ffmpeg.sh [ffmpeg-dir]          # apply and regenerate
#   bash patch_ffmpeg.sh --check [ffmpeg-dir]  # dry-run / validate only

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--check" || "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  shift
fi

FFMPEG_DIR="${1:-third_party/ffmpeg}"

# Chromium 144+: build_ffmpeg.py and generate_gn.py moved to media/ffmpeg/scripts/
BUILD_FFMPEG_PY="media/ffmpeg/scripts/build_ffmpeg.py"
GENERATE_GN_PY="media/ffmpeg/scripts/generate_gn.py"
# copy_config.sh remains in the old location
COPY_CONFIG_SH="$FFMPEG_DIR/chromium/scripts/copy_config.sh"

if [[ ! -d "$FFMPEG_DIR" ]]; then
  echo "ERROR: FFmpeg dir not found: $FFMPEG_DIR" >&2
  exit 1
fi

if [[ ! -f "$BUILD_FFMPEG_PY" ]]; then
  echo "ERROR: build_ffmpeg.py not found: $BUILD_FFMPEG_PY" >&2
  echo "  (expected at media/ffmpeg/scripts/build_ffmpeg.py for Chromium 144+)" >&2
  exit 1
fi

for tool in python3 bash; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: Missing required tool: $tool" >&2
    exit 1
  fi
done

LIBAVCODEC_DIR="$FFMPEG_DIR/libavcodec"
if [[ -d "$LIBAVCODEC_DIR" ]]; then
  if ! ls "$LIBAVCODEC_DIR"/dca*.c >/dev/null 2>&1; then
    echo "WARN: DTS decoder sources (dca*.c) not found in $LIBAVCODEC_DIR"
  fi
  if ! ls "$LIBAVCODEC_DIR"/hevc*.c >/dev/null 2>&1; then
    echo "WARN: HEVC decoder sources (hevc*.c) not found in $LIBAVCODEC_DIR"
  fi
  if [[ ! -f "$LIBAVCODEC_DIR/ac3dec.c" ]]; then
    echo "WARN: AC3 decoder source (ac3dec.c) not found in $LIBAVCODEC_DIR"
  fi
  if ! ls "$LIBAVCODEC_DIR"/eac3*.c >/dev/null 2>&1; then
    echo "WARN: EAC3 decoder sources (eac3*.c) not found in $LIBAVCODEC_DIR"
  fi
fi

DRY_RUN_FLAG=""
if $DRY_RUN; then
  DRY_RUN_FLAG="--check"
fi

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

# Chromium's build_ffmpeg.py uses: configure_flags['Chrome'].extend([
#   '--enable-decoder=aac,h264',
#   '--enable-demuxer=aac',
#   '--enable-parser=aac,h264',
# ])
# Each --enable-<kind>= appears once with comma-separated codec names.
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

if $DRY_RUN; then
  echo "Dry run: skipping ffmpeg config regeneration"
  exit 0
fi

targets=(
  "linux x64"
  "linux arm64"
  "mac x64"
  "mac arm64"
  "win x64"
)

for t in "${targets[@]}"; do
  read -r os arch <<< "$t"
  echo "Running build_ffmpeg.py $os $arch"
  python3 "$BUILD_FFMPEG_PY" "$os" "$arch"
done

bash "$COPY_CONFIG_SH"
python3 "$GENERATE_GN_PY"

echo "Verifying generated ffmpeg config headers"
CHECK_FILE="$FFMPEG_DIR/chromium/config/Chrome/linux/x64/config_components.h"
if [[ -f "$CHECK_FILE" ]]; then
  pass=true
  for flag in CONFIG_HEVC_DECODER CONFIG_AC3_DECODER CONFIG_EAC3_DECODER CONFIG_DCA_DECODER; do
    if ! grep -q "$flag 1" "$CHECK_FILE"; then
      echo "WARN: $flag not set to 1 in $CHECK_FILE"
      pass=false
    fi
  done
  if $pass; then
    echo "All expected decoder flags verified in config_components.h"
  fi
else
  echo "WARN: Could not verify config components: $CHECK_FILE not found"
fi

echo "FFmpeg patching and regeneration complete"
