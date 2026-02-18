#!/usr/bin/env python3

import argparse
import re
import shutil
import sys
from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def backup_once(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".orig")
    if not backup.exists():
        shutil.copy2(path, backup)


def patch_supported_types(text: str):
    """Patch media/base/supported_types.cc to unconditionally enable extra codecs.

    Chromium 144 uses IsDefaultDecoderSupportedAudioType / IsDefaultDecoderSupportedVideoType.
    Older Chromium used IsDefaultSupportedAudioType / IsDefaultSupportedVideoType.
    We accept either name.

    Strategy:
      1. Replace guarded returns (BUILDFLAG / helper function calls) with ``return true;``
      2. If the cases are entirely absent, insert them as fallthrough to existing AAC/H264 paths.
    """
    changed = []

    # ------- sanity checks -------
    audio_fn_found = re.search(r"IsDefault(?:Decoder)?SupportedAudioType", text)
    if not audio_fn_found:
        raise RuntimeError(
            "Could not find IsDefault[Decoder]SupportedAudioType in supported_types.cc"
        )

    video_fn_found = re.search(r"IsDefault(?:Decoder)?SupportedVideoType", text)
    if not video_fn_found:
        raise RuntimeError(
            "Could not find IsDefault[Decoder]SupportedVideoType in supported_types.cc"
        )

    # ------- DTS: kDTS / kDTSXP2 / (optional kDTSE) → return true -------
    # Upstream Chromium 144 pattern:
    #   case AudioCodec::kDTS:
    #   case AudioCodec::kDTSXP2:
    #   case AudioCodec::kDTSE:          ← may or may not be present
    #     return BUILDFLAG(ENABLE_PLATFORM_DTS_AUDIO);
    dts_pat = re.compile(
        r"(?P<cases>"
        r"case\s+AudioCodec::kDTS:\s*\n"
        r"(?:\s*case\s+AudioCodec::kDTSXP2:\s*\n)?"
        r"(?:\s*case\s+AudioCodec::kDTSE:\s*\n)?"
        r"\s*)"
        r"return\s+BUILDFLAG\s*\(\s*ENABLE_PLATFORM_DTS_AUDIO\s*\)\s*;",
        re.MULTILINE,
    )
    text, count = dts_pat.subn(r"\g<cases>return true;", text)
    if count:
        changed.append(f"supported_types.cc: DTS return override x{count}")

    # ------- AC3/EAC3 → return true -------
    # Upstream Chromium 144 pattern:
    #   case AudioCodec::kAC3:
    #   case AudioCodec::kEAC3:
    #     return IsDecoderDolbyAc3Eac3Supported(type);
    ac3_pat = re.compile(
        r"(?P<cases>"
        r"case\s+AudioCodec::kAC3:\s*\n"
        r"\s*case\s+AudioCodec::kEAC3:\s*\n"
        r"\s*)"
        r"return\s+IsDecoderDolbyAc3Eac3Supported\s*\(\s*type\s*\)\s*;",
        re.MULTILINE,
    )
    text, count = ac3_pat.subn(r"\g<cases>return true;", text)
    if count:
        changed.append(f"supported_types.cc: AC3/EAC3 return override x{count}")

    # ------- HEVC → return true -------
    # Upstream Chromium 144 pattern:
    #   case VideoCodec::kHEVC:
    #     return IsDecoderHevcProfileSupported(type);
    hevc_pat = re.compile(
        r"(?P<cases>"
        r"case\s+VideoCodec::kHEVC:\s*\n"
        r"\s*)"
        r"return\s+IsDecoderHevcProfileSupported\s*\(\s*type\s*\)\s*;",
        re.MULTILINE,
    )
    text, count = hevc_pat.subn(r"\g<cases>return true;", text)
    if count:
        changed.append(f"supported_types.cc: HEVC return override x{count}")

    # ------- Fallback insertion: audio codecs -------
    # If the cases were not present at all (already stripped or different layout),
    # insert them before AudioCodec::kAAC as fallthrough.
    if not re.search(r"case\s+AudioCodec::kAC3:", text):
        marker_re = re.compile(r"([ \t]*)(case\s+AudioCodec::kAAC:)")
        m = marker_re.search(text)
        if not m:
            raise RuntimeError("Could not find AudioCodec::kAAC insertion point")
        indent = m.group(1)
        insert = (
            f"{indent}case AudioCodec::kAC3:\n"
            f"{indent}case AudioCodec::kEAC3:\n"
            f"{indent}case AudioCodec::kDTS:\n"
            f"{indent}case AudioCodec::kDTSXP2:\n"
        )
        text = text[: m.start()] + insert + text[m.start() :]
        changed.append(
            "supported_types.cc: inserted AC3/EAC3/DTS/DTSXP2 fallback cases"
        )

    # ------- Fallback insertion: HEVC -------
    if not re.search(r"case\s+VideoCodec::kHEVC:", text):
        marker_re = re.compile(r"([ \t]*)(case\s+VideoCodec::kH264:)")
        m = marker_re.search(text)
        if not m:
            raise RuntimeError("Could not find VideoCodec::kH264 insertion point")
        indent = m.group(1)
        insert = f"{indent}case VideoCodec::kHEVC:\n{indent}  return true;\n"
        text = text[: m.start()] + insert + text[m.start() :]
        changed.append("supported_types.cc: inserted HEVC fallback case")

    return text, changed


def patch_ffmpeg_common(text: str):
    changed = []

    # ------- Codec ID mappings -------
    if (
        "AV_CODEC_ID_AC3" not in text
        or "AV_CODEC_ID_EAC3" not in text
        or "AV_CODEC_ID_DTS" not in text
    ):
        aac_block = r"(case\s+AudioCodec::kAAC:\s*\n\s*return\s+AV_CODEC_ID_AAC;\s*\n)"
        add = (
            "    case AudioCodec::kAC3:\n"
            "      return AV_CODEC_ID_AC3;\n"
            "    case AudioCodec::kEAC3:\n"
            "      return AV_CODEC_ID_EAC3;\n"
            "    case AudioCodec::kDTS:\n"
            "      return AV_CODEC_ID_DTS;\n"
        )
        new_text, count = re.subn(aac_block, r"\1" + add, text, count=1, flags=re.M)
        if count == 0:
            raise RuntimeError("Could not find AAC mapping block in ffmpeg_common.cc")
        text = new_text
        changed.append("ffmpeg_common.cc: inserted AC3/EAC3/DTS codec ID mappings")

    if "AV_CODEC_ID_HEVC" not in text:
        h264_map = r"(case\s+VideoCodec::kH264:\s*\n\s*return\s+AV_CODEC_ID_H264;\s*\n)"
        add = "    case VideoCodec::kHEVC:\n      return AV_CODEC_ID_HEVC;\n"
        new_text, count = re.subn(h264_map, r"\1" + add, text, count=1, flags=re.M)
        if count == 0:
            raise RuntimeError("Could not find H264 mapping block in ffmpeg_common.cc")
        text = new_text
        changed.append("ffmpeg_common.cc: inserted HEVC codec ID mapping")

    # ------- Video decoder allowlist (GetAllowedVideoDecoders) -------
    # Chromium 144 pattern:
    #   return "h264";
    # inside GetAllowedVideoDecoders()
    if '"h264,hevc"' not in text:
        video_pat = re.compile(r'return\s+"h264"\s*;')
        text, count = video_pat.subn('return "h264,hevc";', text, count=1)
        if count:
            changed.append(
                "ffmpeg_common.cc: added hevc to GetAllowedVideoDecoders allowlist"
            )
        else:
            # Already patched or different format — not fatal
            pass

    # ------- Audio decoder allowlist (GetAllowedAudioDecoders) -------
    # Chromium 144 pattern:
    #   #define EXTRA_CODECS ",aac"
    # We add AC3/EAC3/DCA to the EXTRA_CODECS macro.
    if ",ac3" not in text or ",eac3" not in text or ",dca" not in text:
        audio_pat = re.compile(r'#define\s+EXTRA_CODECS\s+",aac"')
        text, count = audio_pat.subn(
            '#define EXTRA_CODECS ",aac,ac3,eac3,dca"', text, count=1
        )
        if count:
            changed.append(
                "ffmpeg_common.cc: added ac3/eac3/dca to GetAllowedAudioDecoders allowlist"
            )
        else:
            # Already patched or different format — not fatal
            pass

    return text, changed


def patch_ffmpeg_video_decoder(text: str):
    """Move HEVC from NOTREACHED group into the multithreaded decode path.

    In upstream Chromium 144 GetFFmpegVideoDecoderThreadCount(), HEVC sits
    in the NOTREACHED() branch.  We:
      1. Remove it from there (if present).
      2. Insert it before kH264 in the multithreaded branch (if not already there).
    """
    changed = []

    # Chromium 144 has kHEVC in the NOTREACHED switch group — remove it from there.
    notreached_hevc = re.compile(
        r"(\n)([ \t]*case\s+VideoCodec::kHEVC:\s*\n)"
        r"(?=(?:[ \t]*case\s+VideoCodec::\w+:\s*\n)*"
        r"[ \t]*(?://[^\n]*\n\s*)*NOTREACHED)",
        re.MULTILINE,
    )
    text, removed = notreached_hevc.subn(r"\1", text, count=1)
    if removed:
        changed.append("ffmpeg_video_decoder.cc: removed HEVC from NOTREACHED group")

    # Insert HEVC into the multithreaded branch if not already there.
    already_ok = re.search(
        r"case\s+VideoCodec::kHEVC:\s*\n\s*case\s+VideoCodec::kH264:", text
    )
    if not already_ok:
        h264_re = re.compile(r"([ \t]*)(case\s+VideoCodec::kH264:)")
        m = h264_re.search(text)
        if not m:
            raise RuntimeError("Could not find H264 case in ffmpeg_video_decoder.cc")
        indent = m.group(1)
        text = (
            text[: m.start()] + f"{indent}case VideoCodec::kHEVC:\n" + text[m.start() :]
        )
        changed.append("ffmpeg_video_decoder.cc: inserted HEVC into multithread branch")

    return text, changed


def patch_ffmpeg_glue_demuxers(text: str):
    """Add AC3/EAC3/DTS standalone demuxers to GetAllowedDemuxers() in ffmpeg_glue.cc.

    Chromium 144 pattern:
        allowed_demuxers.push_back("aac");
    We insert additional push_back calls after it.
    """
    changed = []

    demuxers_to_add = ["ac3", "eac3", "dts"]
    missing = [d for d in demuxers_to_add if f'push_back("{d}")' not in text]

    if missing:
        aac_push = re.compile(
            r'(^[ \t]*allowed_demuxers\.push_back\(\s*"aac"\s*\)\s*;\s*\n)',
            re.MULTILINE,
        )
        m = aac_push.search(text)
        if not m:
            raise RuntimeError("Could not find aac demuxer push_back in ffmpeg_glue.cc")
        indent_match = re.match(r"^(\s*)", m.group(1))
        indent = indent_match.group(1) if indent_match else "    "
        insertion = "".join(
            f'{indent}allowed_demuxers.push_back("{d}");\n' for d in missing
        )
        text = text[: m.end()] + insertion + text[m.end() :]
        changed.append(
            f"ffmpeg_glue.cc: inserted {'/'.join(missing)} demuxer allowlist entries"
        )

    return text, changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch Chromium media layer for extra codecs"
    )
    parser.add_argument(
        "--check",
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Validate and report without writing",
    )
    args = parser.parse_args()

    targets = {
        Path("media/base/supported_types.cc"): patch_supported_types,
        Path("media/ffmpeg/ffmpeg_common.cc"): patch_ffmpeg_common,
        Path("media/filters/ffmpeg_video_decoder.cc"): patch_ffmpeg_video_decoder,
        Path("media/filters/ffmpeg_glue.cc"): patch_ffmpeg_glue_demuxers,
    }

    for p in targets:
        if not p.exists():
            print(f"ERROR: Missing file: {p}", file=sys.stderr)
            return 1

    edits = {}
    summary = []
    try:
        for path, patch_fn in targets.items():
            original = read_text(path)
            patched, changed = patch_fn(original)
            edits[path] = (original, patched, changed)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    for path, (original, patched, changed) in edits.items():
        if original != patched:
            summary.extend(changed)

    if not summary:
        print("No changes needed (already patched).")
        return 0

    if args.dry_run:
        print("Dry run: patches detected and validated.")
        for item in summary:
            print(f"- {item}")
        return 0

    for path, (original, patched, changed) in edits.items():
        if original == patched:
            continue
        backup_once(path)
        write_text(path, patched)

    print("Applied Chromium media patches:")
    for item in summary:
        print(f"- {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
