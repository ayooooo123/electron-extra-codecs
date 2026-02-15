#!/usr/bin/env bash
#
# Usage:
#   cd chromium/src && bash /path/to/apply_all.sh          # apply all patches
#   cd chromium/src && bash /path/to/apply_all.sh --check  # dry-run / validate

set -euo pipefail

DRY_RUN=false
if [[ "${1:-}" == "--check" || "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for req in electron media third_party/ffmpeg; do
  if [[ ! -e "$req" ]]; then
    echo "ERROR: Must run from Chromium src/. Missing: $req" >&2
    exit 1
  fi
done

for tool in python3 bash grep; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: $tool not found" >&2
    exit 1
  fi
done

for script in patch_chromium_media.py patch_ffmpeg.sh; do
  if [[ ! -f "$SCRIPT_DIR/$script" ]]; then
    echo "ERROR: Missing $script in $SCRIPT_DIR" >&2
    exit 1
  fi
done

echo "[1/3] Validating Chromium media patch patterns"
python3 "$SCRIPT_DIR/patch_chromium_media.py" --check

if $DRY_RUN; then
  echo "[2/3] Validating FFmpeg build config patterns"
  bash "$SCRIPT_DIR/patch_ffmpeg.sh" --check third_party/ffmpeg
  echo "Dry run: all patterns validated successfully."
  exit 0
fi

echo "[1/3] Applying Chromium media patches"
python3 "$SCRIPT_DIR/patch_chromium_media.py"

echo "[2/3] Patching FFmpeg build config and regenerating configs"
bash "$SCRIPT_DIR/patch_ffmpeg.sh" third_party/ffmpeg

echo "[3/3] Verifying key patch indicators"

pass=true

if ! grep -q "case VideoCodec::kHEVC:" media/filters/ffmpeg_video_decoder.cc; then
  echo "FAIL: HEVC case not found in ffmpeg_video_decoder.cc"
  pass=false
fi

if ! grep -q "AV_CODEC_ID_AC3" media/ffmpeg/ffmpeg_common.cc; then
  echo "FAIL: AC3 mapping not found in ffmpeg_common.cc"
  pass=false
fi

if ! grep -q "AV_CODEC_ID_DTS" media/ffmpeg/ffmpeg_common.cc; then
  echo "FAIL: DTS mapping not found in ffmpeg_common.cc"
  pass=false
fi

CFG="third_party/ffmpeg/chromium/config/Chrome/linux/x64/config_components.h"
if [[ -f "$CFG" ]]; then
  for flag in CONFIG_HEVC_DECODER CONFIG_AC3_DECODER CONFIG_EAC3_DECODER CONFIG_DCA_DECODER; do
    if ! grep -q "$flag 1" "$CFG"; then
      echo "FAIL: $flag 1 not found in $CFG"
      pass=false
    fi
  done
else
  echo "WARN: $CFG missing, skipping config verification"
fi

if [[ "$pass" != true ]]; then
  echo "Patch verification failed"
  exit 1
fi

cat <<'EOF'

All patches applied successfully.

Next steps:

  export CHROMIUM_BUILDTOOLS_PATH=$(pwd)/buildtools
  gn gen out/Release --args='import("//electron/build/args/release.gn")'
  ninja -C out/Release electron
  electron/script/strip-binaries.py -d out/Release
  ninja -C out/Release electron:electron_dist_zip

Result: out/Release/dist.zip

EOF
