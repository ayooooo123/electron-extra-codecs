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
    "CONFIG_HEVC_SEI",
    "CONFIG_AC3_DECODER",
    "CONFIG_EAC3_DECODER",
    "CONFIG_DCA_DECODER",
    "CONFIG_AC3_FIXED_DECODER",
    "CONFIG_AC3DSP",
    "CONFIG_BSWAPDSP",
    "CONFIG_DOVI_RPU",
    "CONFIG_DTSHD_DEMUXER",
    "CONFIG_DTS_DEMUXER",
    "CONFIG_AC3_DEMUXER",
    "CONFIG_EAC3_DEMUXER",
    "CONFIG_EAC3_CORE_BSF",
    "CONFIG_AC3_PARSER",
    "CONFIG_HEVC_PARSER",
    "CONFIG_DCA_PARSER",
]

CODEC_LIST_ENTRIES = [
    "&ff_hevc_decoder",
    "&ff_ac3_decoder",
    "&ff_eac3_decoder",
    "&ff_dca_decoder",
    "&ff_ac3_fixed_decoder",
]

PARSER_LIST_ENTRIES = [
    "&ff_ac3_parser",
    "&ff_hevc_parser",
    "&ff_dca_parser",
]

DEMUXER_LIST_ENTRIES = [
    "&ff_dtshd_demuxer",
    "&ff_dts_demuxer",
]

# ---------------------------------------------------------------------------
# Source file lists, split by platform.
#
# Modern Chromium FFmpeg (Chromium 130+) reorganised HEVC sources into
# libavcodec/hevc/ sub-directory.  ASM (NASM) and GAS (.S) files must go
# into separate GNI variables (ffmpeg_asm_sources / ffmpeg_gas_sources).
# ---------------------------------------------------------------------------

# Platform-independent C sources (ffmpeg_c_sources, all arches)
EXTRA_C_SOURCES = [
    # -- HEVC decoder core (hevc/ subdirectory) --
    "libavcodec/hevc/hevcdec.c",
    "libavcodec/hevc/cabac.c",
    "libavcodec/hevc/data.c",
    "libavcodec/hevc/dsp.c",
    "libavcodec/hevc/filter.c",
    "libavcodec/hevc/mvs.c",
    "libavcodec/hevc/parse.c",
    "libavcodec/hevc/parser.c",
    "libavcodec/hevc/pred.c",
    "libavcodec/hevc/ps.c",
    "libavcodec/hevc/refs.c",
    "libavcodec/hevc/sei.c",
    # -- HEVC dependencies --
    "libavcodec/aom_film_grain.c",
    "libavcodec/dovi_rpu.c",
    "libavcodec/dovi_rpudec.c",
    "libavcodec/dynamic_hdr_vivid.c",
    "libavcodec/h274.c",
    # -- AC3 / EAC3 --
    "libavcodec/ac3.c",
    "libavcodec/ac3_parser.c",
    "libavcodec/ac3dec_data.c",
    "libavcodec/ac3dec_fixed.c",
    "libavcodec/ac3dec_float.c",
    "libavcodec/ac3dsp.c",
    "libavcodec/ac3tab.c",
    "libavcodec/eac3_data.c",
    "libavcodec/eac3dec.c",
    # -- DCA / DTS --
    "libavcodec/dca.c",
    "libavcodec/dca_core.c",
    "libavcodec/dca_exss.c",
    "libavcodec/dca_lbr.c",
    "libavcodec/dca_parser.c",
    "libavcodec/dca_sample_rate_tab.c",
    "libavcodec/dca_xll.c",
    "libavcodec/dcadata.c",
    "libavcodec/dcadct.c",
    "libavcodec/dcadec.c",
    "libavcodec/dcadsp.c",
    "libavcodec/dcahuff.c",
    # -- Shared DSP helpers --
    "libavcodec/bswapdsp.c",
    "libavcodec/fmtconvert.c",
    "libavcodec/synth_filter.c",
    # -- Demuxers --
    "libavformat/dtsdec.c",
    "libavformat/dtshddec.c",
]

# x86 C init files (ffmpeg_c_sources, x86/x64 only)
EXTRA_X86_C_SOURCES = [
    "libavcodec/x86/ac3dsp_init.c",
    "libavcodec/x86/bswapdsp_init.c",
    "libavcodec/x86/dcadsp_init.c",
    "libavcodec/x86/fmtconvert_init.c",
    "libavcodec/x86/synth_filter_init.c",
    "libavcodec/x86/hevc/dsp_init.c",
    "libavcodec/x86/h26x/h2656dsp.c",
]

# x86 NASM assembly (ffmpeg_asm_sources, x86/x64 only)
EXTRA_X86_ASM_SOURCES = [
    "libavcodec/x86/ac3dsp.asm",
    "libavcodec/x86/ac3dsp_downmix.asm",
    "libavcodec/x86/bswapdsp.asm",
    "libavcodec/x86/dcadsp.asm",
    "libavcodec/x86/fmtconvert.asm",
    "libavcodec/x86/synth_filter.asm",
    "libavcodec/x86/hevc/add_res.asm",
    "libavcodec/x86/hevc/deblock.asm",
    "libavcodec/x86/hevc/idct.asm",
    "libavcodec/x86/hevc/mc.asm",
    "libavcodec/x86/hevc/sao.asm",
    "libavcodec/x86/hevc/sao_10bit.asm",
    "libavcodec/x86/h26x/h2656_inter.asm",
]

# aarch64 C init files (ffmpeg_c_sources, arm64 only)
EXTRA_AARCH64_C_SOURCES = [
    "libavcodec/aarch64/ac3dsp_init_aarch64.c",
    "libavcodec/aarch64/fmtconvert_init.c",
    "libavcodec/aarch64/synth_filter_init.c",
    "libavcodec/aarch64/hevcdsp_init_aarch64.c",
]

# aarch64 GAS assembly (ffmpeg_gas_sources, arm64 only)
EXTRA_AARCH64_GAS_SOURCES = [
    "libavcodec/aarch64/ac3dsp_neon.S",
    "libavcodec/aarch64/fmtconvert_neon.S",
    "libavcodec/aarch64/synth_filter_neon.S",
    "libavcodec/aarch64/hevcdsp_deblock_neon.S",
    "libavcodec/aarch64/hevcdsp_idct_neon.S",
    "libavcodec/aarch64/h26x/epel_neon.S",
    "libavcodec/aarch64/h26x/qpel_neon.S",
    "libavcodec/aarch64/h26x/sao_neon.S",
]

# ---------------------------------------------------------------------------

CHROME_CONFIG_ROOT = Path("third_party/ffmpeg/chromium/config/Chrome")
FFMPEG_ROOT = Path("third_party/ffmpeg")
FFMPEG_GENERATED_GNI = FFMPEG_ROOT / "ffmpeg_generated.gni"
GNI_MARKER = "# Extra codec sources for custom Chrome builds (HEVC, AC3, EAC3, DTS)"

IF_BLOCK_RE = re.compile(r"if\s*\((?P<condition>.*?)\)\s*\{", re.DOTALL)


# ---- GN basename collision handling -------------------------------------


def get_gni_c_basenames(gni_text: str) -> set[str]:
    """Extract basenames of all .c source files already in the GNI."""
    basenames: set[str] = set()
    for match in re.finditer(r'"([^"]+\.c)"', gni_text):
        basenames.add(match.group(1).rsplit("/", 1)[-1])
    return basenames


def resolve_basename_collisions(
    sources: list[str],
    existing_basenames: set[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Replace sources with colliding basenames with wrapper paths.

    GN cannot have two source files producing the same object file name
    in a single target.  For collisions we create thin wrapper .c files
    with unique names that simply ``#include`` the original.

    Returns ``(resolved_sources, wrappers_to_create)``.
    Each wrapper entry is ``(wrapper_gni_path, include_path)``.
    """
    resolved: list[str] = []
    wrappers: list[tuple[str, str]] = []

    for source in sources:
        p = Path(source)
        basename = p.name

        if basename not in existing_basenames:
            resolved.append(source)
            existing_basenames.add(basename)
            continue

        # Collision – build a wrapper with a unique name.
        # e.g. libavcodec/hevc/cabac.c  →  libavcodec/hevc_cabac.c
        parent = p.parent  # libavcodec/hevc
        subdir = parent.name  # hevc
        grandparent = parent.parent  # libavcodec
        wrapper_name = f"{subdir}_{basename}"
        wrapper_path = (grandparent / wrapper_name).as_posix()
        include_path = f"{subdir}/{basename}"

        resolved.append(wrapper_path)
        wrappers.append((wrapper_path, include_path))
        existing_basenames.add(wrapper_name)

    return resolved, wrappers


def create_wrapper_files(
    wrappers: list[tuple[str, str]],
    dry_run: bool = False,
) -> None:
    """Create thin wrapper .c files that ``#include`` the originals."""
    for wrapper_path, include_path in wrappers:
        abs_path = FFMPEG_ROOT / wrapper_path
        if dry_run:
            print(f"  Would create wrapper: {abs_path}")
            continue
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "// Auto-generated wrapper to avoid GN basename collision.\n"
            f'#include "{include_path}"\n'
        )
        write_text(abs_path, content)
        print(f"  Created wrapper: {abs_path} -> {include_path}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def detect_newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


# ---- config_components.h patching ----------------------------------------


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


# ---- codec / parser / demuxer list patching ------------------------------


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


# ---- ffmpeg_generated.gni patching ---------------------------------------


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


def filter_available(sources: list[str], warnings: list[str]) -> list[str]:
    """Return sources whose files exist on disk."""
    available = []
    for source in sources:
        source_path = FFMPEG_ROOT / source
        if source_path.is_file():
            available.append(source)
        else:
            warnings.append(f"WARN: Missing ffmpeg source file: {source_path}")
    return available


def filter_not_in_gni(sources: list[str], gni_text: str) -> list[str]:
    """Return sources not already present (exact path match) in the GNI."""
    return [s for s in sources if f'"{s}"' not in gni_text]


def _format_source_list(
    indent: str,
    var_name: str,
    sources: list[str],
    newline: str,
) -> list[str]:
    """Build lines for a GNI ``var += [ ... ]`` block."""
    lines = [f"{indent}{var_name} += ["]
    for source in sources:
        lines.append(f'{indent}  "{source}",')
    lines.append(f"{indent}]")
    return lines


def build_managed_gni_block(
    c_sources: list[str],
    x86_c_sources: list[str],
    x86_asm_sources: list[str],
    aarch64_c_sources: list[str],
    aarch64_gas_sources: list[str],
    newline: str,
) -> str:
    """Build the complete managed GNI block with platform guards."""
    lines: list[str] = [GNI_MARKER]
    lines.append('if (ffmpeg_branding == "Chrome" || ffmpeg_branding == "ChromeOS") {')

    # platform-independent C sources
    if c_sources:
        lines.extend(_format_source_list("  ", "ffmpeg_c_sources", c_sources, newline))

    # x86 / x64 block
    has_x86 = x86_c_sources or x86_asm_sources
    if has_x86:
        lines.append("")
        lines.append('  if (current_cpu == "x64" ||')
        lines.append('      (is_win && current_cpu == "x86") ||')
        lines.append('      (use_linux_config && current_cpu == "x86")) {')
        if x86_c_sources:
            lines.extend(
                _format_source_list("    ", "ffmpeg_c_sources", x86_c_sources, newline)
            )
        if x86_asm_sources:
            lines.extend(
                _format_source_list(
                    "    ", "ffmpeg_asm_sources", x86_asm_sources, newline
                )
            )
        lines.append("  }")

    # aarch64 block
    has_aarch64 = aarch64_c_sources or aarch64_gas_sources
    if has_aarch64:
        lines.append("")
        lines.append('  if (current_cpu == "arm64" || current_cpu == "arm64e") {')
        if aarch64_c_sources:
            lines.extend(
                _format_source_list(
                    "    ", "ffmpeg_c_sources", aarch64_c_sources, newline
                )
            )
        if aarch64_gas_sources:
            lines.extend(
                _format_source_list(
                    "    ", "ffmpeg_gas_sources", aarch64_gas_sources, newline
                )
            )
        lines.append("  }")

    lines.append("}")
    return newline.join(lines) + newline


def remove_managed_block(text: str) -> str:
    """Remove the existing managed GNI block (marker + following if-block)."""
    marker_pos = text.find(GNI_MARKER)
    if marker_pos == -1:
        return text

    newline = detect_newline(text)

    # Find start of the marker line
    line_start = text.rfind(newline, 0, marker_pos)
    line_start = 0 if line_start == -1 else line_start + len(newline)

    # Find the opening brace of the if-block after the marker
    brace_pos = text.find("{", marker_pos)
    if brace_pos == -1:
        return text

    block_end = find_block_end(text, brace_pos)
    if block_end is None:
        return text

    before = text[:line_start].rstrip(newline)
    after = text[block_end:].lstrip(newline)

    if after:
        return before + newline + after
    return before + newline


def patch_ffmpeg_generated_gni(
    text: str,
    check: bool = False,
) -> tuple[str, int, list[str]]:
    warnings: list[str] = []

    c_sources = filter_available(EXTRA_C_SOURCES, warnings)
    x86_c_sources = filter_available(EXTRA_X86_C_SOURCES, warnings)
    x86_asm_sources = filter_available(EXTRA_X86_ASM_SOURCES, warnings)
    aarch64_c_sources = filter_available(EXTRA_AARCH64_C_SOURCES, warnings)
    aarch64_gas_sources = filter_available(EXTRA_AARCH64_GAS_SOURCES, warnings)

    cleaned_text = remove_managed_block(text)

    c_sources = filter_not_in_gni(c_sources, cleaned_text)
    x86_c_sources = filter_not_in_gni(x86_c_sources, cleaned_text)
    x86_asm_sources = filter_not_in_gni(x86_asm_sources, cleaned_text)
    aarch64_c_sources = filter_not_in_gni(aarch64_c_sources, cleaned_text)
    aarch64_gas_sources = filter_not_in_gni(aarch64_gas_sources, cleaned_text)

    existing_basenames = get_gni_c_basenames(cleaned_text)
    all_wrappers: list[tuple[str, str]] = []

    c_sources, wrappers = resolve_basename_collisions(c_sources, existing_basenames)
    all_wrappers.extend(wrappers)

    x86_c_sources, wrappers = resolve_basename_collisions(
        x86_c_sources,
        existing_basenames,
    )
    all_wrappers.extend(wrappers)

    aarch64_c_sources, wrappers = resolve_basename_collisions(
        aarch64_c_sources,
        existing_basenames,
    )
    all_wrappers.extend(wrappers)

    if all_wrappers:
        create_wrapper_files(all_wrappers, dry_run=check)

    total_added = (
        len(c_sources)
        + len(x86_c_sources)
        + len(x86_asm_sources)
        + len(aarch64_c_sources)
        + len(aarch64_gas_sources)
    )
    if total_added == 0:
        return text, 0, warnings

    newline = detect_newline(cleaned_text)
    block = build_managed_gni_block(
        c_sources,
        x86_c_sources,
        x86_asm_sources,
        aarch64_c_sources,
        aarch64_gas_sources,
        newline,
    )

    if cleaned_text.endswith(newline * 2):
        result = cleaned_text + block
    elif cleaned_text.endswith(newline):
        result = cleaned_text + newline + block
    else:
        result = cleaned_text + newline + newline + block

    return result, total_added, warnings


def patch_ffmpeg_build_gn(check: bool = False) -> list[str]:
    build_gn = FFMPEG_ROOT / "BUILD.gn"
    if not build_gn.is_file():
        return ["WARN: third_party/ffmpeg/BUILD.gn not found"]

    text = read_text(build_gn)

    if '"libavcodec"' in text:
        return []

    target_match = re.search(
        r'target\s*\(\s*link_target_type\s*,\s*"ffmpeg_internal"\s*\)', text
    )
    if not target_match:
        return ["WARN: Could not find ffmpeg_internal target in BUILD.gn"]

    search_start = target_match.end()
    include_match = re.search(r"include_dirs\s*=\s*\[", text[search_start:])
    if not include_match:
        return ["WARN: Could not find include_dirs in ffmpeg_internal target"]

    block_open = search_start + include_match.end() - 1
    block_close = text.find("]", block_open)
    if block_close == -1:
        return ["WARN: Could not parse include_dirs block in BUILD.gn"]

    block = text[block_open : block_close + 1]
    dot_match = re.search(r'^(?P<indent>\s*)"\."\s*,\s*\n', block, re.MULTILINE)
    if not dot_match:
        return ["WARN: Could not find '.' entry in ffmpeg_internal include_dirs"]

    insert_at = block_open + dot_match.end()
    indent = dot_match.group("indent")
    new_text = text[:insert_at] + f'{indent}"libavcodec",\n' + text[insert_at:]

    if not check:
        write_text(build_gn, new_text)

    return ["BUILD.gn: added 'libavcodec' to ffmpeg_internal include_dirs"]


# ---- Orchestration -------------------------------------------------------


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

    # Patch ffmpeg_generated.gni
    gni_text = read_text(FFMPEG_GENERATED_GNI)
    gni_updated, gni_added, gni_warnings = patch_ffmpeg_generated_gni(
        gni_text,
        check=args.check,
    )
    gni_changed = gni_updated != gni_text
    if gni_changed and not args.check:
        write_text(FFMPEG_GENERATED_GNI, gni_updated)
    files_changed += int(gni_changed)
    warnings.extend(gni_warnings)
    print(
        f"Patching ffmpeg_generated.gni: added {gni_added} source entries "
        f"(C + ASM + GAS)"
    )

    for message in patch_ffmpeg_build_gn(args.check):
        print(message)

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
