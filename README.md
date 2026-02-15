# electron-extra-codecs

Patch scripts for Electron v40.4.1 (Chromium 144) to enable software decoding of HEVC (H.265), AC3, EAC3, and DTS in Chromium's media pipeline.

Stock Electron ships with `proprietary_codecs=true` and `ffmpeg_branding="Chrome"`, but common movie codecs like AC3/DTS are still excluded at compile time by ffmpeg config and Chromium media allowlists.

## What This Adds

- HEVC (H.265) software decode
- AC3 (Dolby Digital) software decode
- EAC3 (Dolby Digital Plus) software decode
- DTS software decode (`dca` decoder)

## Quick Start

1) Install depot_tools and sync Electron v40.4.1 source.

```bash
mkdir electron-build && cd electron-build
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git
export PATH="$PWD/depot_tools:$PATH"

gclient config --name "src/electron" --unmanaged https://github.com/electron/electron
gclient sync --with_branch_heads --with_tags

cd src/electron
git checkout v40.4.1
gclient sync -f

cd ..
git clone https://github.com/ayooooo123/electron-extra-codecs.git
cd src
bash ../electron-extra-codecs/scripts/apply_all.sh
```

2) Build Electron.

```bash
export CHROMIUM_BUILDTOOLS_PATH=$(pwd)/buildtools
gn gen out/Release --args='import("//electron/build/args/release.gn")'
ninja -C out/Release electron
electron/script/strip-binaries.py -d out/Release
ninja -C out/Release electron:electron_dist_zip
```

Result: `out/Release/dist.zip`

## How It Works

Three-layer patching:

1. ffmpeg build config (`third_party/ffmpeg/chromium/scripts/build_ffmpeg.py`)
   - Extends Chrome branding decoder/demuxer/parser flags.
2. Chromium media layer (`media/`)
   - Updates media allowlists and ffmpeg codec mappings.
   - Moves HEVC into multithreaded ffmpeg decode path.
3. ffmpeg config regeneration
   - Runs ffmpeg config generation for linux/mac/win targets.
   - Runs `copy_config.sh` and `generate_gn.py`.

## Verify Codec Support

After building patched Electron, check `canPlayType` in renderer devtools:

```javascript
document.createElement("video").canPlayType('video/mp4; codecs="hev1.1.6.L93.B0"')
document.createElement("video").canPlayType('audio/mp4; codecs="ac-3"')
document.createElement("video").canPlayType('audio/mp4; codecs="ec-3"')
```

Expected: non-empty (`"maybe"` or `"probably"`), not `""`.

## Requirements

- Electron source checkout (v40.4.1)
- 100GB+ free disk
- 16GB+ RAM recommended
- Python 3
- Bash
- Build time: typically 4-8 hours per platform

## Dry Run

Validate all patch patterns without modifying files:

```bash
cd src
bash ../electron-extra-codecs/scripts/apply_all.sh --check
```

## CI / Releases

Two CI systems build all 5 platform targets:

| CI | Targets | Runner |
|----|---------|--------|
| **GitHub Actions** (`build.yml`) | linux-x64, linux-arm64, win32-x64 | Self-hosted ARM64 Linux box |
| **Cirrus CI** (`.cirrus.yml`) | darwin-arm64, darwin-x64 | Cirrus CI macOS cloud (free for public repos) |

Both trigger on tag push (`v*`). GitHub Actions creates the release with Linux/Windows zips; Cirrus CI appends macOS zips to the same release via `gh release upload`.

### Self-Hosted Runner Setup

Register one runner on your ARM64 Linux box with label **`electron-builder`**:

| Requirement | Value |
|-------------|-------|
| OS | Ubuntu 22.04+ (arm64) |
| Disk | 200+ GB SSD |
| RAM | 32+ GB |
| Packages | `build-essential python3 git curl` + Chromium deps |

Builds run sequentially (`max-parallel: 1`) since they share one machine.

### Cirrus CI Setup

1. Enable Cirrus CI on the repo at [cirrus-ci.com](https://cirrus-ci.com).
2. Add an encrypted `GITHUB_TOKEN` via Cirrus CI settings (needs `contents: write` on the repo) — replace the placeholder in `.cirrus.yml`.
3. Free tier gives 500 macOS minutes/month (~1 full build). For more, register a [persistent worker](https://cirrus-ci.org/guide/persistent-workers/) on any Mac you have access to.

### Triggering Builds

```bash
# Manual dispatch (GitHub Actions only, any branch)
gh workflow run build.yml -f electron_version=v40.4.1

# Tag-triggered (both CIs, creates a GitHub Release)
git tag v40.4.1-codecs && git push origin v40.4.1-codecs
```

## Credits

- ThaUnknown/electron-chromium-codecs
- ThaUnknown/miru
- 5rahim/electron-media-patch
- Alex313031/thorium

## Legal Notice

HEVC, AC3/EAC3, and DTS are patent-encumbered formats in many jurisdictions. This repository only provides source patch automation. You are responsible for ensuring compliance with all applicable patent and licensing obligations in your region.

## License

LGPL-2.1 (same family as prior art projects in this space).
