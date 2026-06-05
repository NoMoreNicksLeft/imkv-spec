"""
imkv/adapters/netflix.py — Netflix interactive manifest adapter.

Converts a Netflix interactiveVideoMoments JSON (and optional SegmentMap)
into iMKV chapter atoms with MKVScript chapter process data.

Tested against: Black Mirror: Bandersnatch
"""

import json
import random

from imkv.core import (
    el, el_uint, el_str, el_bin,
    ID_EditionEntry, ID_EditionUID, ID_EditionFlagHidden,
    ID_EditionFlagDefault, ID_EditionFlagOrdered,
    ID_ChapterAtom, ID_ChapterUID, ID_ChapterStringUID,
    ID_ChapterTimeStart, ID_ChapterTimeEnd,
    ID_ChapterFlagHidden, ID_ChapterFlagEnabled,
    ID_ChapterDisplay, ID_ChapterString, ID_ChapterLanguage,
    ID_ChapProcess, ID_ChapProcessCodecID,
    ID_ChapProcessCommand, ID_ChapProcessTime, ID_ChapProcessData,
    ID_Chapters,
)


# ── String-enum mappings ──────────────────────────────────────────────────────
# Netflix stores some state variables as string enums rather than integers.
# We map them to integers for the MKVScript Let() primitive.

STRING_ENUMS = {
    "p_ps": {"n": 0, "b": 1, "f": 2, "t": 3},
    "p_pc": {"n": 0, "o": 1, "t": 2},
    "p_vs": {"n": 0, "c": 1, "k": 2, "t": 3},
}


def str_to_int(varname, strval):
    return STRING_ENUMS.get(varname, {}).get(strval, 0)


# ── Precondition translation ──────────────────────────────────────────────────

def translate_precondition(cond):
    """Recursively translate a Netflix precondition tree to MKVScript expression."""
    if not cond:
        return "1"
    op = cond[0]
    if op == "persistentState":
        return f"{cond[1]} != 0"
    if op == "not":
        inner = cond[1] if len(cond) == 2 else ["and"] + list(cond[1:])
        return f"!({translate_precondition(inner)})"
    if op == "and":
        return " && ".join(f"({translate_precondition(c)})" for c in cond[1:])
    if op == "or":
        return " || ".join(f"({translate_precondition(c)})" for c in cond[1:])
    if op == "eql":
        lc, right = cond[1], cond[2]
        if lc[0] == "persistentState":
            var = lc[1]
            if isinstance(right, bool):
                return f"{var} == {'1' if right else '0'}"
            elif isinstance(right, str):
                return f"{var} == {str_to_int(var, right)}  // \"{right}\""
            else:
                return f"{var} == {right}"
        return f"{translate_precondition(lc)} == {right}"
    return "1"


# ── State variable emission ───────────────────────────────────────────────────

def state_to_lets(d, indent="    "):
    lines = []
    for var, val in d.items():
        if isinstance(val, bool):
            lines.append(f"{indent}Let({var}, {'1' if val else '0'});")
        elif isinstance(val, str):
            lines.append(f"{indent}Let({var}, {str_to_int(var, val)}); // \"{val}\"")
        elif isinstance(val, (int, float)):
            lines.append(f"{indent}Let({var}, {int(val)});")
    return lines


# ── Script builder ────────────────────────────────────────────────────────────

def build_scripts(seg_id, seg_data, seg_moments, preconditions,
                  segmentGroups, uid_map, **kwargs):
    """
    Build entry and leave MKVScript strings for a single segment.

    Parameters
    ----------
    seg_id           : str   — Netflix segment identifier
    seg_data         : dict  — segment metadata from SegmentMap
    seg_moments      : list  — moments from interactiveVideoMoments
    preconditions    : dict  — global precondition table
    segmentGroups    : dict  — segment group definitions
    uid_map          : dict  — seg_id -> chapter UID
    timeout_override : int   — if set, override all Menu() timeouts (for testing)
    font             : str   — font name or attachment ref for OSD (future)
    asset_uid_map    : dict  — filename -> attachment UID for image assets
    """
    entry_lines = []
    leave_lines = []

    set_font_uid    = kwargs.get('set_font_uid', None)
    timeout_override = kwargs.get('timeout_override', None)
    asset_uid_map    = kwargs.get('asset_uid_map', None)

    # If this is the first chapter and a font UID is specified, emit SetFont()
    # as the first entry script statement.
    if set_font_uid is not None:
        entry_lines.append(f"    SetFont(attach({set_font_uid})); // OSD font")

    # Entry script: emit Let() for persistent state changes on entry
    for m in seg_moments:
        if m["type"] != "notification:playbackImpression":
            continue
        persistent = m.get("impressionData", {}).get("data", {}).get("persistent", {})
        if not persistent:
            continue
        pre = m.get("precondition", [])
        lets = state_to_lets(persistent)
        if pre:
            entry_lines.append(f"    if ({translate_precondition(pre)}) {{")
            entry_lines += [f"    {l}" for l in lets]
            entry_lines.append("    }")
        else:
            entry_lines += lets

    # Leave script: Menu() for choice moments, GotoAndPlay() for linear segments
    choice_moment = next(
        (m for m in seg_moments if m["type"] == "scene:cs_bs"), None)
    extra_blocks = []

    if choice_moment:
        choices     = choice_moment.get("choices", [])
        ui_display  = choice_moment.get("uiDisplayMS", seg_data.get("endTimeMs", 0))
        ui_hide     = choice_moment.get("uiHideMS", ui_display + 10000)
        default_idx = choice_moment.get("defaultChoiceIndex", 0)

        if timeout_override is not None:
            timeout_s = timeout_override
        else:
            timeout_s = max(1, int((ui_hide - ui_display) / 1000))

        option_lines = []

        for i, choice in enumerate(choices, 1):
            text = choice.get("text", f"Option {i}").title().replace('"', "'")
            cimp = choice.get("impressionData", {}).get("data", {}).get("persistent", {})

            # Image asset reference
            image_clause = ""
            if asset_uid_map:
                img = choice.get("image", {})
                bg  = img.get("styles", {}).get("backgroundImage", "")
                if bg:
                    import re
                    url = re.sub(r'^url\(|\)$', '', bg)
                    fname = url.split("/")[-1]
                    uid   = asset_uid_map.get(fname)
                    if uid:
                        image_clause = f", image: attach({uid}), image-fit: fill-height"

            if "segmentId" in choice:
                target = choice["segmentId"]
                tuid   = uid_map.get(target)
                if tuid is None:
                    option_lines.append(
                        f'        Option("{text}", GotoAndPlay(0){image_clause})')
                    continue
                if cimp:
                    bname  = f"opt_{seg_id}_{i}"
                    blines = ([f"{bname}: {{"]
                              + state_to_lets(cimp)
                              + [f"    GotoAndPlay({tuid}); // -> {target}", "}"])
                    extra_blocks.append("\n".join(blines))
                    option_lines.append(
                        f'        Option("{text}", {bname}{image_clause})')
                else:
                    option_lines.append(
                        f'        Option("{text}", GotoAndPlay({tuid}){image_clause}) // -> {target}')

            elif "sg" in choice:
                sg_name = choice["sg"]
                group   = segmentGroups.get(sg_name, [])
                bname   = f"sg_{seg_id}_{i}"
                blines  = [f"{bname}: {{"]
                if cimp:
                    blines += state_to_lets(cimp)
                cases = []
                for item in group:
                    if isinstance(item, str):
                        pre  = preconditions.get(item, [])
                        cases.append((translate_precondition(pre), item,
                                      uid_map.get(item, 0)))
                    elif isinstance(item, dict):
                        seg  = item.get("segment", "")
                        pre  = preconditions.get(item.get("precondition", ""), [])
                        cases.append((translate_precondition(pre), seg,
                                      uid_map.get(seg, 0)))
                blines.append("    Select {")
                for expr, tseg, tuid in cases:
                    blines.append(
                        f"        Case({expr}) {{ GotoAndPlay({tuid}); }} // -> {tseg}")
                blines += [
                    f'        Default {{ Panic("Unresolved {sg_name} in {seg_id}"); }}',
                    "    }", "}"]
                extra_blocks.append("\n".join(blines))
                option_lines.append(
                    f'        Option("{text}", {bname}{image_clause})')

        if option_lines:
            leave_lines += [
                "entry: {",
                f"    Menu(timeout: {timeout_s}, default: {default_idx + 1},",
            ]
            for j, ol in enumerate(option_lines):
                leave_lines.append(ol + ("," if j < len(option_lines) - 1 else ""))
            leave_lines += ["    );", "}"]
            for eb in extra_blocks:
                leave_lines += ["", eb]

    else:
        dn = seg_data.get("defaultNext")
        if dn and dn in uid_map:
            leave_lines += [
                "entry: {",
                f"    GotoAndPlay({uid_map[dn]}); // -> {dn}",
                "}",
            ]

    entry = ("entry: {\n" + "\n".join(entry_lines) + "\n}") if entry_lines else None
    leave = "\n".join(leave_lines) if leave_lines else None
    return entry, leave


def build_chapter_atom(seg_id, seg_data, seg_moments, preconditions,
                       segmentGroups, uid_map, **kwargs):
    uid      = uid_map[seg_id]
    start_ns = int(seg_data["startTimeMs"]) * 1_000_000
    end_ns   = int(seg_data.get("endTimeMs",
                   seg_data["startTimeMs"] + 1000)) * 1_000_000

    entry_script, leave_script = build_scripts(
        seg_id, seg_data, seg_moments, preconditions,
        segmentGroups, uid_map, **kwargs)

    display   = el(ID_ChapterDisplay,
                   el_str(ID_ChapterString, seg_id)
                   + el_str(ID_ChapterLanguage, "eng"))

    atom_data = (
        el_uint(ID_ChapterUID, uid, 4)
        + el_uint(ID_ChapterTimeStart, start_ns, 8)
        + el_uint(ID_ChapterTimeEnd, end_ns, 8)
        + el_uint(ID_ChapterFlagHidden, 0)
        + el_uint(ID_ChapterFlagEnabled, 1)
        + display
        + el_str(ID_ChapterStringUID, seg_id)
    )

    for script, time_val in [(entry_script, 1), (leave_script, 2)]:
        if script:
            cmd       = el(ID_ChapProcessCommand,
                           el_uint(ID_ChapProcessTime, time_val)
                           + el_bin(ID_ChapProcessData, script.encode('utf-8')))
            atom_data += el(ID_ChapProcess,
                            el_uint(ID_ChapProcessCodecID, 0) + cmd)

    return el(ID_ChapterAtom, atom_data)


def build_chapters(segments, moments_by_seg, preconditions,
                   segmentGroups, **kwargs):
    """
    Build the full Chapters EBML element for a Netflix title.

    Returns (chapters_ebml, uid_map) where uid_map maps seg_id -> chapter UID.
    """
    uid_map     = {seg_id: random.randint(1, 2**32) for seg_id in segments}
    edition_uid = random.randint(1, 2**32)

    # font_uid: if provided, emit SetFont(attach(N)) in the first chapter's
    # entry script so the renderer knows which embedded font to use for OSD.
    font_uid = kwargs.pop('font_uid', None)

    atoms = b""
    total = len(segments)
    first = True
    for i, (seg_id, seg_data) in enumerate(segments.items(), 1):
        if i % 50 == 0:
            print(f"  Chapter {i}/{total}: {seg_id}", flush=True)
        atom_kwargs = dict(kwargs)
        if first and font_uid is not None:
            atom_kwargs['set_font_uid'] = font_uid
            first = False
        atoms += build_chapter_atom(
            seg_id, seg_data,
            moments_by_seg.get(seg_id, []),
            preconditions, segmentGroups,
            uid_map, **atom_kwargs)

    edition = el(ID_EditionEntry,
                 el_uint(ID_EditionUID, edition_uid, 4)
                 + el_uint(ID_EditionFlagHidden, 0)
                 + el_uint(ID_EditionFlagDefault, 1)
                 + el_uint(ID_EditionFlagOrdered, 1)
                 + atoms)
    return el(ID_Chapters, edition), uid_map


def load_manifest(json_path, segmap_path):
    """
    Load a Netflix interactive manifest + segment map.
    Returns (segments, moments_by_seg, preconditions, segmentGroups).
    """
    with open(json_path) as f:
        bdata = json.load(f)
    with open(segmap_path) as f:
        smap = json.load(f)

    # Netflix JSON structure: videos -> {video_id} -> interactiveVideoMoments -> value
    video_id = next(iter(bdata["videos"]))
    info     = bdata["videos"][video_id]["interactiveVideoMoments"]["value"]

    return (
        smap["segments"],
        info["momentsBySegment"],
        info["preconditions"],
        info["segmentGroups"],
    )
