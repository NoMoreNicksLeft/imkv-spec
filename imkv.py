#!/usr/bin/env python3
"""
imkv.py — iMKV conversion tool

Converts a source MKV and an interactive manifest into an iMKV file
with embedded chapter scripts, OSD configuration, and media assets.

Usage:
    python3 imkv.py netflix <source.mkv> <manifest.json> <segmentmap.json> [output.mkv]
                    [--timeout <seconds>]
                    [--font <name-or-path>]
                    [--fetch-assets]
                    [--assets-dir <dir>]
"""

import argparse
import os
import random
import sys
import re

# Ensure imkv package is importable from this directory
sys.path.insert(0, os.path.dirname(__file__))

from imkv.core import rewrite_with_chapters, build_attachments
from imkv.adapters.netflix import build_chapters, load_manifest
from imkv.title import bake as title_bake


WEBP_MIME  = "image/webp"
FONT_MIMES = {
    ".ttf":   "font/ttf",
    ".otf":   "font/otf",
    ".woff":  "font/woff",
    ".woff2": "font/woff2",
}


def fetch_assets(manifest_json_path, assets_dir):
    """
    Download image assets referenced in the Netflix manifest to assets_dir.
    Returns list of local file paths.
    """
    import json
    import urllib.request

    with open(manifest_json_path) as f:
        bdata = json.load(f)
    video_id = next(iter(bdata["videos"]))
    info     = bdata["videos"][video_id]["interactiveVideoMoments"]["value"]

    urls = set()
    for seg, mlist in info["momentsBySegment"].items():
        for m in mlist:
            for c in m.get("choices", []):
                bg = c.get("image", {}).get("styles", {}).get("backgroundImage", "")
                if bg:
                    url = re.sub(r'^url\(|\)$', '', bg)
                    urls.add(url)

    os.makedirs(assets_dir, exist_ok=True)
    paths = []
    for url in sorted(urls):
        fname = url.split("/")[-1]
        dest  = os.path.join(assets_dir, fname)
        if os.path.exists(dest):
            print(f"  Asset already present: {fname}")
        else:
            print(f"  Fetching: {fname} ...")
            urllib.request.urlretrieve(url, dest)
        paths.append(dest)
    return paths


def build_attachment_list(asset_paths, font_path=None):
    """
    Build list of attachment dicts for core.build_attachments().
    Assigns UIDs sequentially starting from 1.
    """
    files = []
    uid   = 1

    for path in asset_paths:
        fname = os.path.basename(path)
        ext   = os.path.splitext(fname)[1].lower()
        mime  = FONT_MIMES.get(ext, WEBP_MIME)
        with open(path, 'rb') as f:
            data = f.read()
        files.append({
            'uid':         uid,
            'filename':    fname,
            'mime_type':   mime,
            'data':        data,
            'description': 'iMKV interactive asset',
        })
        print(f"  Attachment {uid}: {fname} ({len(data):,} bytes, {mime})")
        uid += 1

    if font_path and os.path.isfile(font_path):
        fname = os.path.basename(font_path)
        ext   = os.path.splitext(fname)[1].lower()
        mime  = FONT_MIMES.get(ext, "font/otf")
        with open(font_path, 'rb') as f:
            data = f.read()
        files.append({
            'uid':         uid,
            'filename':    fname,
            'mime_type':   mime,
            'data':        data,
            'description': 'iMKV OSD font',
        })
        print(f"  Attachment {uid}: {fname} ({len(data):,} bytes, {mime}) [font]")

    return files


def cmd_fetch_assets(args):
    import json
    from imkv.title import fetch_attachment, _asset_cache_dir

    with open(args.title) as f:
        title = json.load(f)

    cache_dir = _asset_cache_dir(args.title)
    print(f"Fetching assets for: {title.get('title', args.title)}")
    print(f"Cache directory: {cache_dir}")

    ok = skipped = failed = 0
    for att in title.get("attachments", []):
        fname = att.get("filename", "")
        if not att.get("_source_url"):
            skipped += 1
            continue
        data, info = fetch_attachment(att, args.title)
        if data is None:
            print(f"  FAILED: {fname}: {info}")
            failed += 1
        else:
            ok += 1

    print(f"\nDone. {ok} downloaded/cached, {skipped} skipped (no URL), {failed} failed.")


def cmd_bake(args):
    source_path = args.source
    title_path  = args.title
    out_path    = args.output or source_path.rsplit('.mkv', 1)[0] + '_imkv.mkv'

    if not os.path.exists(source_path):
        print(f"Error: source file not found: {source_path}")
        sys.exit(1)
    if not os.path.exists(title_path):
        print(f"Error: title JSON not found: {title_path}")
        sys.exit(1)

    print(f"Baking: {title_path} + {source_path} -> {out_path}")
    title_bake(title_path, source_path, out_path)


def cmd_netflix(args):
    source_path = args.source
    json_path   = args.manifest
    segmap_path = args.segmentmap
    out_path    = args.output or source_path.rsplit('.mkv', 1)[0] + '_imkv.mkv'

    if not os.path.exists(source_path):
        print(f"Error: source file not found: {source_path}")
        sys.exit(1)

    # Fetch assets if requested
    asset_paths  = []
    assets_dir   = args.assets_dir or os.path.join(
                       os.path.dirname(__file__), 'assets')

    if args.fetch_assets:
        print("Fetching image assets...")
        asset_paths = fetch_assets(json_path, assets_dir)
    else:
        # Use any assets already present in the assets dir
        if os.path.isdir(assets_dir):
            asset_paths = [
                os.path.join(assets_dir, f)
                for f in os.listdir(assets_dir)
                if not f.startswith('.') and os.path.isfile(
                    os.path.join(assets_dir, f))
            ]
            if asset_paths:
                print(f"Using {len(asset_paths)} existing asset(s) from {assets_dir}")

    # Build attachments
    attachments_ebml = None
    asset_uid_map    = {}  # filename -> uid

    font_path = None
    if args.font and os.path.isfile(args.font):
        font_path = args.font
    elif args.font:
        print(f"  Note: --font '{args.font}' is a font name, not a file path. "
              f"Specify a file path to embed the font.")

    if asset_paths or font_path:
        print("\nBuilding attachments...")
        att_list = build_attachment_list(asset_paths, font_path)
        attachments_ebml, att_uid_map = build_attachments(att_list)
        # Map just the filename (not full path) to uid
        asset_uid_map = {os.path.basename(k): v for k, v in att_uid_map.items()}
        print(f"  Attachments element: {len(attachments_ebml):,} bytes")

    # Load manifest
    print("\nLoading manifest...")
    segments, moments_by_seg, preconditions, segmentGroups = \
        load_manifest(json_path, segmap_path)
    print(f"  {len(segments)} segments")

    # Build chapters
    print(f"\nBuilding chapters...")

    # Find font attachment UID if a font was embedded
    font_uid = None
    if font_path:
        fname = os.path.basename(font_path)
        font_uid = asset_uid_map.get(fname)
        if font_uid:
            print(f"  Font attachment UID: {font_uid} ({fname})")

    chapters_ebml, uid_map = build_chapters(
        segments, moments_by_seg, preconditions, segmentGroups,
        timeout_override=args.timeout,
        font=args.font,
        asset_uid_map=asset_uid_map if asset_uid_map else None,
        font_uid=font_uid,
    )
    print(f"  Chapters element: {len(chapters_ebml):,} bytes")

    # Write output
    print()
    rewrite_with_chapters(source_path, chapters_ebml, out_path,
                          attachments_ebml=attachments_ebml)

    print(f"\nComplete.")
    print(f"  {len(uid_map)} segments encoded.")
    print(f"  Output: {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Convert source MKV + interactive manifest to iMKV format.")
    subparsers = parser.add_subparsers(dest="adapter", required=True)

    # fetch-assets subcommand
    fa = subparsers.add_parser("fetch-assets",
        help="Pre-download all remote assets referenced in a title JSON")
    fa.add_argument("title", help="Title JSON file")

    # bake subcommand
    bk = subparsers.add_parser("bake",
        help="Bake a title JSON + source MKV into an iMKV file")
    bk.add_argument("title",  help="Title JSON file")
    bk.add_argument("source", help="Source MKV file")
    bk.add_argument("-o", "--output", default=None,
                    help="Output path (default: source_imkv.mkv)")

    # netflix subcommand
    nf = subparsers.add_parser("netflix",
        help="Convert a Netflix interactive title")
    nf.add_argument("source",     help="Source MKV file")
    nf.add_argument("manifest",   help="Netflix interactiveVideoMoments JSON")
    nf.add_argument("segmentmap", help="Segment map JSON")
    nf.add_argument("output",     nargs="?",
                    help="Output path (default: source_imkv.mkv)")
    nf.add_argument("--timeout",  type=int, default=None,
                    metavar="SECONDS",
                    help="Override all Menu() timeouts (useful for testing)")
    nf.add_argument("--font",     default=None,
                    metavar="NAME-OR-PATH",
                    help="Font name (informational) or path to font file to embed")
    nf.add_argument("--fetch-assets", action="store_true",
                    help="Download image assets from the manifest CDN URLs")
    nf.add_argument("--assets-dir", default=None,
                    metavar="DIR",
                    help="Directory for image assets (default: ./assets/)")

    args = parser.parse_args()

    if args.adapter == "fetch-assets":
        cmd_fetch_assets(args)
    elif args.adapter == "bake":
        cmd_bake(args)
    elif args.adapter == "netflix":
        cmd_netflix(args)


if __name__ == "__main__":
    main()
