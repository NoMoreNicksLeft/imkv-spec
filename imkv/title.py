"""
title.py — iMKV title JSON schema and bake logic

The title JSON is the authoritative source for an iMKV conversion.
It contains both the structural layer (branching logic, chapter UIDs,
state variables) and the presentation layer (menu styles, positions,
indicators, asset references).

Workflow:
    1. Run the Netflix adapter to generate a structural skeleton JSON.
    2. Hand-edit the JSON to add presentation (styles, positions, libass markup).
    3. Run `imkv.py bake title.json source.mkv -o output.mkv` to produce the MKV.

The MKV is a build artifact — always rebake from the JSON rather than
editing the MKV directly.
"""

from __future__ import annotations
import json
import os
import struct
import zlib
import urllib.request
import urllib.error
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# 1×1 transparent PNG — hardcoded, no external dependency
# ─────────────────────────────────────────────────────────────────────────────

def _make_1x1_png() -> bytes:
    """Generate a minimal 1×1 fully-transparent PNG."""
    sig  = b'\x89PNG\r\n\x1a\n'
    # IHDR: width=1, height=1, bitdepth=8, colortype=6 (RGBA)
    ihdr_data = struct.pack('>II', 1, 1) + bytes([8, 6, 0, 0, 0])
    ihdr_crc  = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    # IDAT: filter byte 0 + RGBA(0,0,0,0)
    compressed = zlib.compress(b'\x00\x00\x00\x00\x00')
    idat_crc   = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
    idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
    # IEND
    iend_crc = zlib.crc32(b'IEND') & 0xffffffff
    iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
    return sig + ihdr + idat + iend

_1X1_PNG = _make_1x1_png()

IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp", "image/gif",
               "image/bmp", "image/tiff"}
IMAGE_EXTS  = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}

# ─────────────────────────────────────────────────────────────────────────────
# Schema version
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_VERSION = 1


# ─────────────────────────────────────────────────────────────────────────────
# Default / empty structures
# ─────────────────────────────────────────────────────────────────────────────

def empty_indicator() -> dict:
    return {"type": "none"}


def empty_style() -> dict:
    """A named style definition, referenced by style_ref in menus."""
    return {
        "style": "none",            # none | libass | image
        "selected": empty_indicator(),
        "unselected": empty_indicator(),
    }


def empty_option(text: str = "", goto_uid: int = 0) -> dict:
    return {
        "text": text,               # semantic label, always present
        # image: {"attach": "filename.webp"}  — optional
        # x, y, width, height: floats (percentage of frame)
        "goto": goto_uid,           # chapter UID (int) or chapter name (str)
    }


def empty_menu(timeout: int = 10, default: int = 1) -> dict:
    return {
        "timeout": timeout,
        "default": default,
        "style_ref": None,          # name of a style in the title's styles dict
        # Inline style override (overrides style_ref if present):
        # "style": "none" | "libass" | "image"
        # "selected": indicator_spec
        # "unselected": indicator_spec
        "options": [],
    }


def empty_chapter(uid: int, start: str = "00:00:00.000",
                  end: str = "00:00:00.000", name: str = "") -> dict:
    return {
        "uid": uid,
        "name": name,
        "start": start,
        "end": end,
        "enter": None,   # script string or None
        "leave": None,   # script string, menu dict, or None
    }


def empty_title() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "title": "",
        "attachments": [],          # list of {"filename": ..., "mime": ...}
        "styles": {},               # name -> style dict
        "chapters": [],             # list of chapter dicts (ordered by virtual timeline)
    }


# ─────────────────────────────────────────────────────────────────────────────
# Indicator serialisation
# ─────────────────────────────────────────────────────────────────────────────

def format_indicator(ind: dict) -> str:
    """
    Render an indicator spec into iMKV script syntax.
    ind may be:
      {"type": "none"}
      {"type": "libass", "markup": "...", "x_offset": 0, "y_offset": 6}
      {"type": "image",  "attach": "filename.webp", "x_offset": 0, "y_offset": 6}
    """
    t = ind.get("type", "none")
    if t == "none":
        return "none"
    x = ind.get("x_offset", 0)
    y = ind.get("y_offset", 0)
    if t == "libass":
        markup = ind.get("markup", "")
        escaped = markup.replace('"', '\\"')
        return f'{{ libass: "{escaped}", x_offset: {x}%, y_offset: {y}% }}'
    if t == "image":
        attach_name = ind.get("attach", "")
        return f'{{ image: attach("{attach_name}"), x_offset: {x}%, y_offset: {y}% }}'
    return "none"


# ─────────────────────────────────────────────────────────────────────────────
# Script generation from chapter dicts
# ─────────────────────────────────────────────────────────────────────────────

def render_menu(menu: dict, styles: dict, attach_index: dict) -> str:
    """
    Render a menu dict into a Menu() script call.

    attach_index maps filename -> attachment uid (int).
    """
    timeout = menu.get("timeout", 10)
    default = menu.get("default", 1)

    # Resolve style — inline takes precedence over style_ref
    style_name = menu.get("style", None)
    selected_ind = menu.get("selected", None)
    unselected_ind = menu.get("unselected", None)

    # Always resolve style_ref for indicators, even if style is set inline
    if menu.get("style_ref"):
        ref = styles.get(menu["style_ref"], {})
        if style_name is None:
            style_name = ref.get("style", "none")
        if selected_ind is None:
            selected_ind = ref.get("selected", {"type": "none"})
        if unselected_ind is None:
            unselected_ind = ref.get("unselected", {"type": "none"})

    if style_name is None:
        style_name = "none"
    if selected_ind is None:
        selected_ind = {"type": "none"}
    if unselected_ind is None:
        unselected_ind = {"type": "none"}

    # Resolve attach() references: replace filename strings with numeric UIDs
    def resolve_attach(ind: dict) -> dict:
        if ind.get("type") == "image":
            fname = ind.get("attach", "")
            uid = attach_index.get(fname, fname)
            return {**ind, "attach_uid": uid}
        if ind.get("type") == "libass":
            fname = ind.get("attach", "")
            if fname:
                uid = attach_index.get(fname, fname)
                return {**ind, "attach_uid": uid}
        return ind

    selected_ind = resolve_attach(selected_ind)
    unselected_ind = resolve_attach(unselected_ind)

    def format_ind_resolved(ind: dict) -> str:
        t = ind.get("type", "none")
        if t == "none":
            return "none"
        x = ind.get("x_offset", 0)
        y = ind.get("y_offset", 0)
        if t == "libass":
            markup = ind.get("markup", "")
            escaped = markup.replace('"', '\\"')
            return f'{{ libass: "{escaped}", x_offset: {x}%, y_offset: {y}% }}'
        if t == "image":
            uid = ind.get("attach_uid", ind.get("attach", ""))
            return f'{{ image: attach({uid}), x_offset: {x}%, y_offset: {y}% }}'
        return "none"

    lines = [
        f"    Menu(timeout: {timeout}, default: {default},",
        f"        style: {style_name},",
        f"        selected: {format_ind_resolved(selected_ind)},",
        f"        unselected: {format_ind_resolved(unselected_ind)},",
    ]

    for opt in menu.get("options", []):
        text = opt.get("text", "")
        goto = opt.get("goto", 0)
        image = opt.get("image", None)
        x = opt.get("x", None)
        y = opt.get("y", None)
        w = opt.get("width", None)
        h = opt.get("height", None)

        # Resolve goto — may be a chapter name or UID int
        if isinstance(goto, str):
            # Will be resolved to UID by the caller
            goto_str = f"GotoAndPlay(__UID_{goto}__)"
        else:
            goto_str = f"GotoAndPlay({goto})"

        opt_parts = [f'text: "{text}"']
        if image:
            fname = image.get("attach", "")
            uid = attach_index.get(fname, fname)
            opt_parts.append(f"image: attach({uid})")
        if x is not None:
            opt_parts.append(f"x: {x}%")
        if y is not None:
            opt_parts.append(f"y: {y}%")
        if w is not None:
            opt_parts.append(f"width: {w}%")
        if h is not None:
            opt_parts.append(f"height: {h}%")
        opt_parts.append(goto_str)

        lines.append(f"        Option({', '.join(opt_parts)}),")

    lines.append("    );")
    return "\n".join(lines)


def render_leave(leave: Any, styles: dict, attach_index: dict) -> str:
    """
    Render a leave value into a script string.
    leave may be:
      - None            → empty
      - str             → raw script
      - dict with "menu" key → Menu() call
    """
    if leave is None:
        return ""
    if isinstance(leave, str):
        return leave
    if isinstance(leave, dict):
        if "menu" in leave:
            menu_script = render_menu(leave["menu"], styles, attach_index)
            return f"entry: {{\n{menu_script}\n}}"
        # Inline script fragments
        if "script" in leave:
            return leave["script"]
    return ""


def render_enter(enter: Any) -> str:
    if enter is None:
        return ""
    if isinstance(enter, str):
        return enter
    return ""


def _mkv_has_image_attachment(mkv_path: str) -> bool:
    """
    Return True if the source MKV already contains at least one image attachment.
    Checks MIME types stored in the Attachments element.
    """
    try:
        import subprocess
        result = subprocess.run(
            ['mkvmerge', '--identify', '--identification-format', 'json', mkv_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode not in (0, 1):
            return False
        info = json.loads(result.stdout)
        for att in info.get('attachments', []):
            mime = att.get('content_type', '')
            fname = att.get('file_name', '')
            ext = os.path.splitext(fname)[1].lower()
            if mime in IMAGE_MIMES or ext in IMAGE_EXTS:
                return True
        return False
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Asset downloading
# ─────────────────────────────────────────────────────────────────────────────

def _asset_cache_dir(title_path: str) -> str:
    """
    Return the asset cache directory for a title JSON.
    Stored next to the JSON: <title_stem>_assets/
    Files are never deleted automatically — they serve as a hedge
    against remote URLs disappearing.
    """
    stem = os.path.splitext(os.path.abspath(title_path))[0]
    return stem + "_assets"


def fetch_attachment(att: dict, title_path: str) -> tuple[bytes | None, str]:
    """
    Locate or download an attachment's file data.

    Resolution order:
      1. Explicit 'path' field in the attachment dict (absolute or relative
         to the title JSON directory).
      2. File named 'filename' in the title JSON directory.
      3. File named 'filename' in the asset cache directory.
      4. Download from '_source_url' into the asset cache directory.

    Returns (data, resolved_path) or (None, error_message).
    Never deletes cached files.
    """
    fname     = att.get("filename", "")
    title_dir = os.path.dirname(os.path.abspath(title_path))
    cache_dir = _asset_cache_dir(title_path)

    # 1. Explicit path
    explicit = att.get("path", "")
    if explicit:
        p = explicit if os.path.isabs(explicit) else os.path.join(title_dir, explicit)
        if os.path.exists(p):
            with open(p, "rb") as f:
                return f.read(), p
        return None, f"explicit path not found: {p}"

    # 2. Next to JSON
    p = os.path.join(title_dir, fname)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return f.read(), p

    # 3. Asset cache
    cached = os.path.join(cache_dir, fname)
    if os.path.exists(cached):
        with open(cached, "rb") as f:
            return f.read(), cached

    # 4. Download
    url = att.get("_source_url", "")
    if not url:
        # Special case: 1x1.png is generated internally, never needs a URL
        if fname == "1x1.png":
            return _1X1_PNG, "(generated)"
        return None, f"not found and no _source_url: {fname}"

    os.makedirs(cache_dir, exist_ok=True)
    print(f"  Downloading: {fname}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "imkv/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with open(cached, "wb") as f:
            f.write(data)
        print(f"    -> cached at {cached} ({len(data):,} bytes)")
        return data, cached
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} downloading {url}"
    except Exception as e:
        return None, f"download failed ({e}): {url}"


# ─────────────────────────────────────────────────────────────────────────────
# Bake: title JSON → chapter EBML + attachments
# ─────────────────────────────────────────────────────────────────────────────

def bake(title_path: str, source_path: str, output_path: str) -> None:
    """
    Read a title JSON and source MKV, produce an iMKV output MKV.
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from imkv.core import rewrite_with_chapters, build_attachments

    with open(title_path) as f:
        title = json.load(f)

    title_dir = os.path.dirname(os.path.abspath(title_path))
    styles    = title.get("styles", {})

    # ── Build attachments ─────────────────────────────────────────────────────
    att_list = []
    uid_counter = 1
    attach_index = {}  # filename -> uid

    # Check whether the source MKV already has an image attachment.
    # If not, and our title JSON adds images, we prepend a 1x1 transparent
    # PNG as the very first image so players don't use a menu asset as poster.
    source_has_image = _mkv_has_image_attachment(source_path)

    # Collect resolved attachment data first so we can inspect MIME types
    resolved = []  # list of (att_dict, data)
    for att in title.get("attachments", []):
        data, info = fetch_attachment(att, title_path)
        if data is None:
            print(f"  Warning: skipping attachment '{att.get('filename','?')}': {info}")
        else:
            resolved.append((att, data))

    # Determine if any of our attachments are images
    def _is_image_att(att: dict) -> bool:
        mime = att.get("mime", "")
        ext  = os.path.splitext(att.get("filename", ""))[1].lower()
        return mime in IMAGE_MIMES or ext in IMAGE_EXTS

    title_has_image = any(_is_image_att(a) for a, _ in resolved)

    # Prepend 1x1 PNG if needed: source has no images, but we're adding some
    if title_has_image and not source_has_image:
        # Only prepend if 1x1 isn't already first in the list
        first_is_placeholder = (
            resolved
            and resolved[0][0].get("filename", "") == "1x1.png"
        )
        if not first_is_placeholder:
            print("  Prepending 1x1 transparent PNG (no existing image attachment in source)")
            placeholder_att = {
                "filename": "1x1.png",
                "mime": "image/png",
                "description": "Transparent placeholder (prevents VLC thumbnail)",
            }
            resolved.insert(0, (placeholder_att, _1X1_PNG))
    elif not title_has_image and not source_has_image:
        # No images at all — still prepend 1x1 so future bakes that add images
        # don't accidentally promote a non-placeholder to poster position
        pass  # nothing to do; no images means no poster problem

    # Build the final attachment list
    for att, data in resolved:
        fname = att["filename"]
        mime  = att.get("mime")
        if not mime:
            ext  = os.path.splitext(fname)[1].lower()
            mime = {".ttf": "font/ttf", ".otf": "font/otf",
                    ".png": "image/png", ".webp": "image/webp",
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg"
                   }.get(ext, "application/octet-stream")
        att_list.append({
            "uid":         uid_counter,
            "filename":    fname,
            "mime_type":   mime,
            "data":        data,
            "description": att.get("description", "iMKV asset"),
        })
        attach_index[fname] = uid_counter
        print(f"  Attachment {uid_counter}: {fname} ({len(data):,} bytes, {mime})")
        uid_counter += 1

    attachments_ebml = None
    if att_list:
        attachments_ebml, _ = build_attachments(att_list)

    # ── Build chapters ────────────────────────────────────────────────────────
    # Build a name→uid map for goto resolution
    name_to_uid = {}
    for ch in title.get("chapters", []):
        if ch.get("name") and ch.get("uid"):
            name_to_uid[ch["name"]] = ch["uid"]

    # Generate chapter EBML directly from chapter dicts
    from imkv.core import build_chapters_from_title
    chapters_ebml, uid_map = build_chapters_from_title(
        title.get("chapters", []),
        styles,
        attach_index,
        name_to_uid,
    )

    print(f"  Chapters element: {len(chapters_ebml):,} bytes")

    # ── Write output ──────────────────────────────────────────────────────────
    rewrite_with_chapters(source_path, chapters_ebml, output_path,
                          attachments_ebml=attachments_ebml)

    print(f"\nComplete. Output: {output_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Skeleton export: Netflix adapter → title JSON
# ─────────────────────────────────────────────────────────────────────────────

def export_skeleton(segments, moments_by_seg, preconditions, segmentGroups,
                    timeout_override=None, font=None,
                    asset_uid_map=None, font_uid=None) -> dict:
    """
    Build a title JSON skeleton from Netflix adapter data.
    Presentation fields (style, positions, indicators) are left as defaults
    for the author to fill in.
    """
    from imkv.adapters.netflix import build_chapters as netflix_build_chapters

    # We reuse the existing chapter builder to get the script text per chapter,
    # then parse it back into structured form.
    # For now, emit raw script strings — the author can restructure them into
    # menu dicts manually or with a future parse pass.
    chapters_ebml, uid_map = netflix_build_chapters(
        segments, moments_by_seg, preconditions, segmentGroups,
        timeout_override=timeout_override,
        font=font,
        asset_uid_map=asset_uid_map,
        font_uid=font_uid,
    )

    # Build skeleton: one chapter per segment, with raw scripts
    title = empty_title()
    title["title"] = ""  # author fills in
    title["_note"] = (
        "Generated skeleton. Fill in 'styles' and add "
        "x/y/width/height/style to menu options before baking."
    )

    # Attachments: author adds these manually based on assets
    # (we don't know local paths at this stage)
    title["attachments"] = [
        {"filename": "1x1.png",  "mime": "image/png",
         "description": "Transparent placeholder (prevents thumbnail)"},
    ]
    if font:
        fname = os.path.basename(font) if os.path.isfile(font) else font
        title["attachments"].append({
            "filename": fname,
            "mime": "font/otf",
            "description": "Menu OSD font",
        })

    # Default style — author customises
    title["styles"]["default"] = {
        "style": "none",
        "selected": {"type": "none"},
        "unselected": {"type": "none"},
        "_note": "Change style to 'libass' or 'image' and add indicator specs",
    }

    # Chapters: one per segment in uid_map order
    # We store the raw script as a string; author can later convert to
    # structured menu dicts for presentation control
    for name, uid in uid_map.items():
        seg = next((s for s in segments if s.get("id") == name), None)
        ch = empty_chapter(uid, name=name)
        if seg:
            ch["start"] = seg.get("start_time", "00:00:00.000")
            ch["end"]   = seg.get("end_time",   "00:00:00.000")
        # Raw scripts stored as strings — author edits presentation inline
        # (A future tool could parse these and generate structured menu dicts)
        title["chapters"].append(ch)

    return title
