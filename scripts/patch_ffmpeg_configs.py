#!/usr/bin/env python3

import argparse
import re
import sys
from pathlib import Path


TARGETS = [
    ("linux", "x64"),
    ("linux", "arm64"),
    ("mac", "x64"),
    ("mac", "arm64"),
    ("win", "x64"),
]

CONFIG_FLAGS = [
    "CONFIG_HEVC_DECODER",
    "CONFIG_AC3_DECODER",
    "CONFIG_EAC3_DECODER",
    "CONFIG_DCA_DECODER",
    "CONFIG_MPEG4_DECODER",
    "CONFIG_MPEGVIDEO_DECODER",
    "CONFIG_MP2_DECODER",
    "CONFIG_MP1_DECODER",
    "CONFIG_FLAC_DECODER",
    "CONFIG_AC3_FIXED_DECODER",
    "CONFIG_MP2FLOAT_DECODER",
    "CONFIG_MP1FLOAT_DECODER",
    "CONFIG_MP3_DECODER",
    "CONFIG_MP3FLOAT_DECODER",
    "CONFIG_HEVC_V2_DECODER",
    "CONFIG_DTSHD_DEMUXER",
    "CONFIG_DTS_DEMUXER",
    "CONFIG_AVI_DEMUXER",
    "CONFIG_MPEGVIDEO_DEMUXER",
    "CONFIG_M4V_DEMUXER",
    "CONFIG_H264_DEMUXER",
    "CONFIG_VC1_DEMUXER",
    "CONFIG_FLAC_DEMUXER",
    "CONFIG_HEVC_DEMUXER",
    "CONFIG_MPEG4VIDEO_PARSER",
    "CONFIG_MPEGVIDEO_PARSER",
    "CONFIG_AC3_PARSER",
    "CONFIG_H261_PARSER",
    "CONFIG_VC1_PARSER",
    "CONFIG_H263_PARSER",
    "CONFIG_FLAC_PARSER",
    "CONFIG_HEVC_PARSER",
    "CONFIG_DCA_PARSER",
]

CODEC_LIST_ENTRIES = [
    "&ff_hevc_decoder",
    "&ff_ac3_decoder",
    "&ff_eac3_decoder",
    "&ff_dca_decoder",
    "&ff_mpeg4_decoder",
    "&ff_mpegvideo_decoder",
    "&ff_mp1_decoder",
    "&ff_mp1float_decoder",
    "&ff_mp2_decoder",
    "&ff_mp2float_decoder",
    "&ff_mp3_decoder",
    "&ff_mp3float_decoder",
    "&ff_flac_decoder",
    "&ff_ac3_fixed_decoder",
]

PARSER_LIST_ENTRIES = [
    "&ff_mpeg4video_parser",
    "&ff_mpegvideo_parser",
    "&ff_ac3_parser",
    "&ff_h261_parser",
    "&ff_vc1_parser",
    "&ff_h263_parser",
    "&ff_flac_parser",
    "&ff_hevc_parser",
    "&ff_dca_parser",
]

DEMUXER_LIST_ENTRIES = [
    "&ff_dtshd_demuxer",
    "&ff_dts_demuxer",
    "&ff_avi_demuxer",
    "&ff_mpegvideo_demuxer",
    "&ff_m4v_demuxer",
    "&ff_h264_demuxer",
    "&ff_vc1_demuxer",
    "&ff_flac_demuxer",
    "&ff_hevc_demuxer",
]

EXTRA_GNI_SOURCES = [
    "libavcodec/hevc/hevcdec.c",
    "libavcodec/hevc/hevc_cabac.c",
    "libavcodec/hevc/hevc_filter.c",
    "libavcodec/hevc/hevc_mvs.c",
    "libavcodec/hevc/hevc_parse.c",
    "libavcodec/hevc/hevc_parser.c",
    "libavcodec/hevc/hevc_ps.c",
    "libavcodec/hevc/hevc_refs.c",
    "libavcodec/hevc/hevc_sei.c",
    "libavcodec/hevc/hevc_data.c",
    "libavcodec/ac3dec_float.c",
    "libavcodec/ac3dec_data.c",
    "libavcodec/ac3.c",
    "libavcodec/ac3tab.c",
    "libavcodec/ac3_parser.c",
    "libavcodec/ac3dec_fixed.c",
    "libavcodec/eac3dec.c",
    "libavcodec/eac3_data.c",
    "libavcodec/dca.c",
    "libavcodec/dca_core.c",
    "libavcodec/dca_exss.c",
    "libavcodec/dca_lbr.c",
    "libavcodec/dca_parser.c",
    "libavcodec/dca_xll.c",
    "libavcodec/dcadata.c",
    "libavcodec/dcadec.c",
    "libavcodec/dcadsp.c",
    "libavcodec/dcahuff.c",
    "libavformat/dtshddec.c",
    "libavformat/dtsdec.c",
    "libavformat/avidec.c",
    "libavformat/m4vdec.c",
    "libavformat/h264dec.c",
    "libavformat/vc1dec.c",
    "libavformat/flacdec.c",
    "libavformat/hevcdec.c",
    "libavformat/mpegvideodec.c",
]

CHROME_CONFIG_ROOT = Path("third_party/ffmpeg/chromium/config/Chrome")
FFMPEG_ROOT = Path("third_party/ffmpeg")
FFMPEG_GENERATED_GNI = FFMPEG_ROOT / "ffmpeg_generated.gni"
GNI_MARKER = "# Extra codec sources for custom Chrome builds (HEVC, AC3, EAC3, DTS)"

IF_BLOCK_RE = re.compile(r"if\s*\((?P<condition>.*?)\)\s*\{", re.DOTALL)
LIST_ENTRY_RE = re.compile(r'^\s*"(?P<path>[^"\n]+\.c)",\s*$', re.MULTILINE)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def patch_config_components(text: str) -> tuple[str, int]:
    patched = text
    enabled_count = 0
    for flag in CONFIG_FLAGS:
        pattern = re.compile(
            rf"(^\s*#define\s+{re.escape(flag)}\s+)0(\b.*$)",
            re.MULTILINE,
        )
        patched, replacements = pattern.subn(r"\g<1>1\g<2>", patched)
        enabled_count += replacements
    return patched, enabled_count


def patch_list_file(text: str, entries: list[str]) -> tuple[str, int]:
    missing_entries = [
        entry
        for entry in entries
        if not re.search(rf"^\s*{re.escape(entry)}\s*,\s*$", text, re.MULTILINE)
    ]
    if not missing_entries:
        return text, 0

    lines = text.splitlines(keepends=True)
    null_index = None
    for index, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if re.match(r"^\s*NULL\s*[,}; ]*(?://.*)?$", stripped):
            null_index = index
            break

    if null_index is None:
        raise RuntimeError("Could not find NULL terminator in list file")

    null_line = lines[null_index]
    indent_match = re.match(r"^(\s*)NULL\b", null_line)
    indent = indent_match.group(1) if indent_match else "    "
    newline = detect_newline(text)

    inserted_lines = [f"{indent}{entry},{newline}" for entry in missing_entries]
    lines[null_index:null_index] = inserted_lines
    return "".join(lines), len(missing_entries)


def find_block_end(text: str, opening_brace_index: int) -> int | None:
    depth = 0
    for index in range(opening_brace_index, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def find_chrome_branding_blocks(text: str) -> list[tuple[int, int]]:
    blocks = []
    for match in IF_BLOCK_RE.finditer(text):
        condition = match.group("condition")
        if "ffmpeg_branding" not in condition:
            continue
        if '"Chrome"' not in condition and '"ChromeOS"' not in condition:
            continue

        opening_brace_index = text.find("{", match.start(), match.end())
        if opening_brace_index == -1:
            continue
        block_end = find_block_end(text, opening_brace_index)
        if block_end is None:
            continue
        blocks.append((match.start(), block_end))
    return blocks


def extract_c_sources(text: str) -> set[str]:
    return {match.group("path") for match in LIST_ENTRY_RE.finditer(text)}


def insert_into_managed_gni_block(text: str, sources: list[str]) -> str | None:
    lines = text.splitlines(keepends=True)
    marker_index = None
    for index, line in enumerate(lines):
        if GNI_MARKER in line:
            marker_index = index
            break

    if marker_index is None:
        return None

    list_start = None
    for index in range(marker_index, len(lines)):
        stripped = lines[index].rstrip("\r\n")
        if re.match(r"^\s*ffmpeg_c_sources\s*\+=\s*\[\s*$", stripped):
            list_start = index
            break

    if list_start is None:
        return None

    list_end = None
    for index in range(list_start + 1, len(lines)):
        stripped = lines[index].rstrip("\r\n")
        if re.match(r"^\s*\]\s*$", stripped):
            list_end = index
            break

    if list_end is None:
        return None

    entry_indent = None
    for index in range(list_start + 1, list_end):
        stripped = lines[index].rstrip("\r\n")
        match = re.match(r'^(\s*)"[^"\n]+",\s*$', stripped)
        if match:
            entry_indent = match.group(1)
            break

    if entry_indent is None:
        close_indent_match = re.match(r"^(\s*)\]", lines[list_end])
        close_indent = close_indent_match.group(1) if close_indent_match else "  "
        entry_indent = f"{close_indent}  "

    newline = detect_newline(text)
    insert_lines = [f'{entry_indent}"{source}",{newline}' for source in sources]
    lines[list_end:list_end] = insert_lines
    return "".join(lines)


def append_managed_gni_block(text: str, sources: list[str]) -> str:
    newline = detect_newline(text)
    block_lines = [
        GNI_MARKER,
        'if (ffmpeg_branding == "Chrome" || ffmpeg_branding == "ChromeOS") {',
        "  ffmpeg_c_sources += [",
    ]
    block_lines.extend([f'    "{source}",' for source in sources])
    block_lines.extend(["  ]", "}"])
    block_text = newline.join(block_lines) + newline

    if text.endswith(newline * 2):
        return text + block_text
    if text.endswith(newline):
        return text + newline + block_text
    return text + newline + newline + block_text


def patch_ffmpeg_generated_gni(text: str) -> tuple[str, int, list[str]]:
    warnings = []
    available_sources = []
    for source in EXTRA_GNI_SOURCES:
        source_path = FFMPEG_ROOT / source
        if source_path.is_file():
            available_sources.append(source)
        else:
            warnings.append(f"WARN: Missing ffmpeg source file: {source_path}")

    all_existing_sources = extract_c_sources(text)
    existing_basenames = {Path(source).name for source in all_existing_sources}

    sources_to_add = []
    added_basenames = set()
    for source in available_sources:
        if source in all_existing_sources:
            continue
        base_name = Path(source).name
        if base_name in existing_basenames or base_name in added_basenames:
            warnings.append(
                f"WARN: Skipping {source} due to duplicate object basename: {base_name}"
            )
            continue
        sources_to_add.append(source)
        added_basenames.add(base_name)

    if not sources_to_add:
        return text, 0, warnings

    updated_text = insert_into_managed_gni_block(text, sources_to_add)
    if updated_text is None:
        updated_text = append_managed_gni_block(text, sources_to_add)

    return updated_text, len(sources_to_add), warnings


def apply_patch(path: Path, patcher, check: bool) -> tuple[int, bool]:
    original = read_text(path)
    updated, change_count = patcher(original)
    changed = updated != original
    if changed and not check:
        write_text(path, updated)
    return change_count, changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Patch Chromium FFmpeg generated configs for extra codecs"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate and report changes without writing",
    )
    args = parser.parse_args()

    if not CHROME_CONFIG_ROOT.is_dir():
        print(
            "ERROR: Must be run from Chromium src/ directory "
            "(missing third_party/ffmpeg/chromium/config/Chrome)",
            file=sys.stderr,
        )
        return 1

    if not FFMPEG_GENERATED_GNI.is_file():
        print(
            f"ERROR: Missing required file: {FFMPEG_GENERATED_GNI}",
            file=sys.stderr,
        )
        return 1

    warnings = []
    total_enabled_flags = 0
    total_codec_entries = 0
    total_parser_entries = 0
    total_demuxer_entries = 0
    files_changed = 0

    for os_name, arch in TARGETS:
        platform = f"{os_name}/{arch}"
        platform_dir = CHROME_CONFIG_ROOT / os_name / arch

        if not platform_dir.is_dir():
            warnings.append(
                f"WARN: Missing config directory for {platform}: {platform_dir}"
            )
            continue

        config_components = platform_dir / "config_components.h"
        if config_components.is_file():
            enabled, changed = apply_patch(
                config_components,
                patch_config_components,
                args.check,
            )
            total_enabled_flags += enabled
            files_changed += int(changed)
            print(
                f"Patching config_components.h for {platform}: enabled {enabled} flags"
            )
        else:
            warnings.append(f"WARN: Missing file for {platform}: {config_components}")

        codec_list = platform_dir / "libavcodec" / "codec_list.c"
        if codec_list.is_file():
            added, changed = apply_patch(
                codec_list,
                lambda text: patch_list_file(text, CODEC_LIST_ENTRIES),
                args.check,
            )
            total_codec_entries += added
            files_changed += int(changed)
            print(f"Patching codec_list.c for {platform}: added {added} entries")
        else:
            warnings.append(f"WARN: Missing file for {platform}: {codec_list}")

        parser_list = platform_dir / "libavcodec" / "parser_list.c"
        if parser_list.is_file():
            added, changed = apply_patch(
                parser_list,
                lambda text: patch_list_file(text, PARSER_LIST_ENTRIES),
                args.check,
            )
            total_parser_entries += added
            files_changed += int(changed)
            print(f"Patching parser_list.c for {platform}: added {added} entries")
        else:
            warnings.append(f"WARN: Missing file for {platform}: {parser_list}")

        demuxer_list = platform_dir / "libavformat" / "demuxer_list.c"
        if demuxer_list.is_file():
            added, changed = apply_patch(
                demuxer_list,
                lambda text: patch_list_file(text, DEMUXER_LIST_ENTRIES),
                args.check,
            )
            total_demuxer_entries += added
            files_changed += int(changed)
            print(f"Patching demuxer_list.c for {platform}: added {added} entries")
        else:
            warnings.append(f"WARN: Missing file for {platform}: {demuxer_list}")

    gni_added, gni_changed = 0, False
    gni_warnings = []
    gni_text = read_text(FFMPEG_GENERATED_GNI)
    gni_updated, gni_added, gni_warnings = patch_ffmpeg_generated_gni(gni_text)
    if gni_updated != gni_text:
        gni_changed = True
        if not args.check:
            write_text(FFMPEG_GENERATED_GNI, gni_updated)
    files_changed += int(gni_changed)
    warnings.extend(gni_warnings)
    print(
        f"Patching ffmpeg_generated.gni: added {gni_added} source files for Chrome branding"
    )

    for warning in warnings:
        print(warning)

    print(
        "Summary: "
        f"enabled {total_enabled_flags} flags, "
        f"added {total_codec_entries} codec entries, "
        f"added {total_parser_entries} parser entries, "
        f"added {total_demuxer_entries} demuxer entries, "
        f"added {gni_added} ffmpeg sources, "
        f"updated {files_changed} files"
    )

    if args.check:
        print("Check mode: no files written")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
