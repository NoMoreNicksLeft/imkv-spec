"""
imkv/core.py — EBML/MKV manipulation primitives.

Handles encoding, decoding, SeekHead management, Chapters insertion,
Cues patching, and attachment embedding. Format-agnostic: knows nothing
about Netflix, Bandersnatch, or any specific title.
"""

import os
import struct


# ── EBML element IDs ──────────────────────────────────────────────────────────

ID_EBML                = 0x1A45DFA3
ID_Segment             = 0x18538067
ID_SeekHead            = 0x114D9B74
ID_Void                = 0xEC
ID_Chapters            = 0x1043A770
ID_Attachments         = 0x1941A469
ID_AttachedFile        = 0x61A7
ID_FileDescription     = 0x467E
ID_FileName            = 0x466E
ID_FileMimeType        = 0x4660
ID_FileData            = 0x465C
ID_FileUID             = 0x46AE

ID_EditionEntry        = 0x45B9
ID_EditionUID          = 0x45BC
ID_EditionFlagHidden   = 0x45BD
ID_EditionFlagDefault  = 0x45DB
ID_EditionFlagOrdered  = 0x45DD
ID_ChapterAtom         = 0xB6
ID_ChapterUID          = 0x73C4
ID_ChapterStringUID    = 0x5654
ID_ChapterTimeStart    = 0x91
ID_ChapterTimeEnd      = 0x92
ID_ChapterFlagHidden   = 0x98
ID_ChapterFlagEnabled  = 0x4598
ID_ChapterDisplay      = 0x80
ID_ChapterString       = 0x85
ID_ChapterLanguage     = 0x437C
ID_ChapProcess         = 0x6944
ID_ChapProcessCodecID  = 0x6955
ID_ChapProcessCommand  = 0x6911
ID_ChapProcessTime     = 0x6922
ID_ChapProcessData     = 0x6933

ID_CUES                = 0x1C53BB6B
ID_CUE_POINT           = 0xBB
ID_CUE_TRACK_POS       = 0xB7
ID_CUE_CLUSTER_POS     = 0xF1

KNOWN_IDS = {
    bytes([0x15, 0x49, 0xa9, 0x66]): "Info",
    bytes([0x16, 0x54, 0xae, 0x6b]): "Tracks",
    bytes([0x1c, 0x53, 0xbb, 0x6b]): "Cues",
    bytes([0x12, 0x54, 0xc3, 0x67]): "Tags",
    bytes([0x10, 0x43, 0xa7, 0x70]): "Chapters",
    bytes([0x11, 0x4d, 0x9b, 0x74]): "SeekHead",
    bytes([0x19, 0x41, 0xa4, 0x69]): "Attachments",
}


# ── EBML encoding ─────────────────────────────────────────────────────────────

def vint(value):
    if value < 0x7F:
        return bytes([value | 0x80])
    elif value < 0x3FFF:
        return struct.pack('>H', value | 0x4000)
    elif value < 0x1FFFFF:
        return struct.pack('>I', value | 0x200000)[1:]
    elif value < 0x0FFFFFFF:
        return struct.pack('>I', value | 0x10000000)
    elif value < 0x07FFFFFFFF:
        return struct.pack('>Q', value | 0x0800000000)[3:]
    elif value < 0x03FFFFFFFFFF:
        return struct.pack('>Q', value | 0x040000000000)[2:]
    elif value < 0x01FFFFFFFFFFFF:
        return struct.pack('>Q', value | 0x02000000000000)[1:]
    else:
        return struct.pack('>Q', value | 0x0100000000000000)


def vint_size(value):
    if value < 0x7F:           return 1
    elif value < 0x3FFF:       return 2
    elif value < 0x1FFFFF:     return 3
    elif value < 0x0FFFFFFF:   return 4
    elif value < 0x07FFFFFFFF: return 5
    else:                      return 6


def eid(element_id):
    if element_id <= 0xFF:       return bytes([element_id])
    elif element_id <= 0xFFFF:   return struct.pack('>H', element_id)
    elif element_id <= 0xFFFFFF: return struct.pack('>I', element_id)[1:]
    else:                        return struct.pack('>I', element_id)


def eid_size(element_id):
    if element_id <= 0xFF:       return 1
    elif element_id <= 0xFFFF:   return 2
    elif element_id <= 0xFFFFFF: return 3
    else:                        return 4


def el(element_id, data):
    return eid(element_id) + vint(len(data)) + data


def el_uint(element_id, value, min_size=1):
    size = max(min_size, (value.bit_length() + 7) // 8) if value > 0 else min_size
    return el(element_id, value.to_bytes(size, 'big'))


def el_str(element_id, text):
    return el(element_id, text.encode('utf-8'))


def el_bin(element_id, data):
    return el(element_id, data)


def content_size_for_void_total(total):
    """Find content_size such that a Void element exactly fills total bytes."""
    void_id_sz = eid_size(ID_Void)
    for c in range(total - void_id_sz - 1, -1, -1):
        if void_id_sz + vint_size(c) + c == total:
            return c
    return None


# ── EBML decoding ─────────────────────────────────────────────────────────────

def read_vint(f):
    first = f.read(1)
    if not first: return None, 0
    b = first[0]
    if b & 0x80: return b & 0x7F, 1
    elif b & 0x40: return ((b & 0x3F) << 8) | f.read(1)[0], 2
    elif b & 0x20:
        rest = f.read(2)
        return ((b & 0x1F) << 16) | (rest[0] << 8) | rest[1], 3
    elif b & 0x10:
        rest = f.read(3)
        return ((b & 0x0F) << 24) | (rest[0] << 16) | (rest[1] << 8) | rest[2], 4
    elif b & 0x08:
        rest = f.read(4)
        val = b & 0x07
        for byte in rest: val = (val << 8) | byte
        return val, 5
    elif b & 0x04:
        rest = f.read(5)
        val = b & 0x03
        for byte in rest: val = (val << 8) | byte
        return val, 6
    elif b & 0x02:
        rest = f.read(6)
        val = b & 0x01
        for byte in rest: val = (val << 8) | byte
        return val, 7
    else:
        rest = f.read(7)
        val = 0
        for byte in rest: val = (val << 8) | byte
        return val, 8


def read_element_id(f):
    first = f.read(1)
    if not first: return None, 0
    b = first[0]
    if b & 0x80: return b, 1
    elif b & 0x40: return (b << 8) | f.read(1)[0], 2
    elif b & 0x20:
        rest = f.read(2)
        return (b << 16) | (rest[0] << 8) | rest[1], 3
    else:
        rest = f.read(3)
        return (b << 24) | (rest[0] << 16) | (rest[1] << 8) | rest[2], 4


# ── SeekHead ──────────────────────────────────────────────────────────────────

def parse_seekhead(data):
    """Parse SeekHead content. Returns list of (id_bytes, relative_position)."""
    entries = []
    pos = 0
    while pos < len(data):
        b = data[pos]
        if b & 0x80:   seek_id = b;                             idl = 1
        elif b & 0x40: seek_id = (b << 8) | data[pos + 1];     idl = 2
        else: break
        pos += idl

        b = data[pos]
        if b & 0x80:   sz = b & 0x7F;                               szl = 1
        elif b & 0x40: sz = ((b & 0x3F) << 8) | data[pos + 1];     szl = 2
        else:          sz = b & 0x7F;                               szl = 1
        pos += szl

        if seek_id != 0x4DBB:
            pos += sz
            continue

        content = data[pos:pos + sz]
        pos += sz

        seek_id_bytes = seek_pos = None
        spos = 0
        while spos < len(content):
            b = content[spos]
            if b == 0x53 and spos + 1 < len(content):
                b2 = content[spos + 1]
                if b2 == 0xAB:
                    spos += 2
                    b = content[spos]
                    if b & 0x80:   ssz = b & 0x7F; spos += 1
                    elif b & 0x40: ssz = ((b & 0x3F) << 8) | content[spos + 1]; spos += 2
                    else:          ssz = b & 0x7F; spos += 1
                    seek_id_bytes = bytes(content[spos:spos + ssz])
                    spos += ssz
                elif b2 == 0xAC:
                    spos += 2
                    b = content[spos]
                    if b & 0x80:   ssz = b & 0x7F; spos += 1
                    elif b & 0x40: ssz = ((b & 0x3F) << 8) | content[spos + 1]; spos += 2
                    else:          ssz = b & 0x7F; spos += 1
                    seek_pos = int.from_bytes(content[spos:spos + ssz], 'big')
                    spos += ssz
                else:
                    spos += 1
            else:
                spos += 1

        if seek_id_bytes is not None and seek_pos is not None:
            entries.append((seek_id_bytes, seek_pos))

    return entries


def build_seek_entry(id_bytes, relative_pos):
    seek_id_el  = el_bin(0x53AB, id_bytes)
    pos_bytes   = relative_pos.to_bytes(max(1, (relative_pos.bit_length() + 7) // 8), 'big')
    seek_pos_el = el_bin(0x53AC, pos_bytes)
    return el(0x4DBB, seek_id_el + seek_pos_el)


def build_seekhead(entries):
    content = b""
    for id_bytes, pos in entries:
        content += build_seek_entry(id_bytes, pos)
    return el(ID_SeekHead, content)


def chapters_id_bytes():
    return bytes([0x10, 0x43, 0xA7, 0x70])


def attachments_id_bytes():
    return bytes([0x19, 0x41, 0xA4, 0x69])


# ── Source file scanner ───────────────────────────────────────────────────────

def scan_source(filepath):
    """
    Read the source file's SeekHead and surrounding structure.
    Returns dict with segment_body_start, seekhead_offset, seekhead_total,
    void_total, insertion_offset, original_entries.
    """
    with open(filepath, 'rb') as f:
        elem_id, id_len = read_element_id(f)
        size, size_len = read_vint(f)
        f.seek(id_len + size_len + size)

        seg_id, seg_id_len = read_element_id(f)
        seg_size, seg_size_len = read_vint(f)
        segment_body_start = f.tell()

        sh_offset = f.tell()
        sh_id, sh_id_len = read_element_id(f)
        if sh_id != ID_SeekHead:
            raise ValueError(f"Expected SeekHead at {sh_offset}, got 0x{sh_id:X}")
        sh_size, sh_size_len = read_vint(f)
        sh_header_size = sh_id_len + sh_size_len
        sh_content = f.read(sh_size)
        sh_total = sh_header_size + sh_size

        while True:
            elem_offset = f.tell()
            elem_id, id_len = read_element_id(f)
            if elem_id != ID_Void:
                insertion_offset = elem_offset
                break
            size, size_len = read_vint(f)
            f.seek(elem_offset + id_len + size_len + size)

        void_total = insertion_offset - (sh_offset + sh_total)
        entries = parse_seekhead(sh_content)

        return {
            'segment_body_start': segment_body_start,
            'seekhead_offset':    sh_offset,
            'seekhead_total':     sh_total,
            'void_total':         void_total,
            'insertion_offset':   insertion_offset,
            'original_entries':   entries,
        }


def fix_segment_size(filepath):
    """Rewrite the Segment size field to reflect actual file size."""
    actual_size = os.path.getsize(filepath)
    with open(filepath, 'rb') as f:
        header = f.read(60)
    b = header[4]
    if b & 0x80:   ebml_szl = 1
    elif b & 0x40: ebml_szl = 2
    else:          ebml_szl = 1
    ebml_sz = header[4] & (0x7F >> (ebml_szl - 1))
    if ebml_szl == 2:
        ebml_sz = ((ebml_sz) << 8) | header[5]
    ebml_end = 4 + ebml_szl + ebml_sz
    seg_size_offset  = ebml_end + 4
    seg_body_start   = seg_size_offset + 8
    correct_seg_size = actual_size - seg_body_start
    new_size_bytes   = struct.pack('>Q', correct_seg_size | 0x0100000000000000)
    with open(filepath, 'r+b') as f:
        f.seek(seg_size_offset)
        f.write(new_size_bytes)
    return correct_seg_size


# ── Cues patcher ──────────────────────────────────────────────────────────────

def find_cues_position(filepath, seg_body_start):
    with open(filepath, 'rb') as f:
        f.seek(seg_body_start)
        while True:
            elem_start = f.tell()
            elem_id, id_len = read_element_id(f)
            if elem_id is None:
                break
            size, size_len = read_vint(f)
            content_start = f.tell()
            if elem_id == ID_CUES:
                return elem_start, content_start, size
            if size == (1 << 56) - 1:
                break
            f.seek(content_start + size)
    return None, None, None


def patch_cues(filepath, seg_body_start, insertion_rel_offset, shift_amount):
    """
    Shift all KaxCueClusterPosition values >= insertion_rel_offset by shift_amount.
    Rewrites the Cues element in-place; the element may grow by a few bytes
    at the end of the file, in which case the segment size is updated.
    """
    elem_start, content_start, cues_size = find_cues_position(filepath, seg_body_start)
    if elem_start is None:
        print("  WARNING: Could not find Cues element — cluster positions not patched!")
        return 0

    print(f"  Cues element at file offset {elem_start}, content size {cues_size:,} bytes")

    with open(filepath, 'rb') as f:
        f.seek(content_start)
        original = bytearray(f.read(cues_size))

    out = bytearray()
    pos = 0
    patched = 0

    def decode_vint(buf, p):
        b = buf[p]
        if b & 0x80: return b & 0x7F, 1
        if b & 0x40: return ((b & 0x3F) << 8) | buf[p + 1], 2
        if b & 0x20: return ((b & 0x1F) << 16) | (buf[p + 1] << 8) | buf[p + 2], 3
        return ((b & 0x0F) << 24) | (buf[p + 1] << 16) | (buf[p + 2] << 8) | buf[p + 3], 4

    def decode_eid(buf, p):
        b = buf[p]
        if b & 0x80: return b, 1
        if b & 0x40: return (b << 8) | buf[p + 1], 2
        if b & 0x20: return (b << 16) | (buf[p + 1] << 8) | buf[p + 2], 3
        return (b << 24) | (buf[p + 1] << 16) | (buf[p + 2] << 8) | buf[p + 3], 4

    def encode_uint_min(v):
        nb = max(1, (v.bit_length() + 7) // 8)
        return vint(nb) + v.to_bytes(nb, 'big')

    def patch_cue_track_pos(buf):
        nonlocal patched
        result = bytearray()
        p = 0
        while p < len(buf):
            tid, tlen = decode_eid(buf, p);  p += tlen
            tsz, tszl = decode_vint(buf, p); p += tszl
            val_bytes = buf[p:p + tsz]
            if tid == ID_CUE_CLUSTER_POS:
                cur = int.from_bytes(val_bytes, 'big')
                new = cur + shift_amount if cur >= insertion_rel_offset else cur
                result += bytes([tid]) + encode_uint_min(new)
                patched += 1
            else:
                result += bytes([tid]) + buf[p - tszl:p] + val_bytes
            p += tsz
        return bytes(result)

    def patch_cue_point(buf):
        result = bytearray()
        p = 0
        while p < len(buf):
            cid, clen = decode_eid(buf, p);  p += clen
            csz, cszl = decode_vint(buf, p); p += cszl
            inner = buf[p:p + csz]
            if cid == ID_CUE_TRACK_POS:
                new_inner = patch_cue_track_pos(inner)
                result += eid(cid) + vint(len(new_inner)) + new_inner
            else:
                result += bytes([cid]) + buf[p - cszl:p] + inner
            p += csz
        return bytes(result)

    while pos < len(original):
        eid_val, eid_len = decode_eid(original, pos); pos += eid_len
        esz, eszl = decode_vint(original, pos);        pos += eszl
        inner = original[pos:pos + esz]
        if eid_val == ID_CUE_POINT:
            new_inner = patch_cue_point(inner)
            out += eid(ID_CUE_POINT) + vint(len(new_inner)) + new_inner
        else:
            out += bytes([eid_val]) + original[pos - eszl:pos] + inner
        pos += esz

    new_cues_elem     = eid(ID_CUES) + vint(len(out)) + bytes(out)
    old_cues_elem_size = (content_start - elem_start) + cues_size
    size_delta        = len(new_cues_elem) - old_cues_elem_size

    with open(filepath, 'r+b') as f:
        f.seek(elem_start)
        f.write(new_cues_elem)

    if size_delta != 0:
        fix_segment_size(filepath)
        print(f"  Cues grew by {size_delta} bytes; segment size updated")

    print(f"  Patched {patched} CueClusterPosition entries")
    return patched


# ── Attachment builder ────────────────────────────────────────────────────────

def build_attached_file(uid, filename, mime_type, data, description=""):
    """Build a single AttachedFile element."""
    content = b""
    if description:
        content += el_str(ID_FileDescription, description)
    content += el_str(ID_FileName, filename)
    content += el_str(ID_FileMimeType, mime_type)
    content += el_bin(ID_FileData, data)
    content += el_uint(ID_FileUID, uid, 4)
    return el(ID_AttachedFile, content)


def build_attachments(files):
    """
    Build an Attachments element.
    files: list of dicts with keys: uid, filename, mime_type, data, description (opt)
    Returns (attachments_ebml, {filename: uid})
    """
    content = b""
    uid_map = {}
    for f in files:
        content += build_attached_file(
            f['uid'], f['filename'], f['mime_type'],
            f['data'], f.get('description', ''))
        uid_map[f['filename']] = f['uid']
    return el(ID_Attachments, content), uid_map


# ── MKV rewriter ──────────────────────────────────────────────────────────────

def rewrite_with_chapters(source_path, chapters_ebml, out_path,
                           attachments_ebml=None, verbose=True):
    """
    Write a new MKV file with Chapters (and optionally Attachments) inserted.
    Updates SeekHead entries and Cues cluster positions accordingly.
    """
    source_size = os.path.getsize(source_path)
    chunk_size  = 8 * 1024 * 1024

    if verbose: print("Scanning source file structure...")
    info = scan_source(source_path)

    seg_body_start   = info['segment_body_start']
    sh_offset        = info['seekhead_offset']
    sh_total         = info['seekhead_total']
    void_total       = info['void_total']
    insertion_offset = info['insertion_offset']
    orig_entries     = info['original_entries']

    # Combined insert: Chapters + optional Attachments
    insert_ebml = chapters_ebml
    if attachments_ebml:
        insert_ebml += attachments_ebml
    insert_size = len(insert_ebml)

    space_for_seekhead = sh_total + void_total

    if verbose:
        print(f"  Segment body starts at: {seg_body_start}")
        print(f"  SeekHead at {sh_offset}, total {sh_total} bytes")
        print(f"  Inserting at offset: {insertion_offset}")
        print(f"  Insert size: {insert_size:,} bytes")

    chapters_rel = insertion_offset - seg_body_start
    new_entries = []
    for id_bytes, rel_pos in orig_entries:
        abs_pos = seg_body_start + rel_pos
        if abs_pos >= insertion_offset:
            new_entries.append((id_bytes, rel_pos + insert_size))
        else:
            new_entries.append((id_bytes, rel_pos))

    new_entries.append((chapters_id_bytes(), chapters_rel))
    if attachments_ebml:
        new_entries.append((attachments_id_bytes(),
                            chapters_rel + len(chapters_ebml)))

    new_sh      = build_seekhead(new_entries)
    new_sh_size = len(new_sh)

    if new_sh_size >= space_for_seekhead:
        raise ValueError(
            f"New SeekHead ({new_sh_size}B) doesn't fit in available space ({space_for_seekhead}B)")

    remaining        = space_for_seekhead - new_sh_size
    void_content_sz  = content_size_for_void_total(remaining)
    if void_content_sz is None:
        raise ValueError(f"Cannot fit Void into {remaining} bytes")

    new_void  = eid(ID_Void) + vint(void_content_sz) + bytes(void_content_sz)
    total_used = new_sh_size + len(new_void)
    assert total_used == space_for_seekhead

    if verbose: print(f"\nWriting output: {out_path}")

    written = 0
    with open(source_path, 'rb') as src, open(out_path, 'wb') as dst:

        # Copy up to SeekHead
        remaining_bytes = sh_offset
        while remaining_bytes > 0:
            data = src.read(min(chunk_size, remaining_bytes))
            if not data: break
            dst.write(data); written += len(data)
            remaining_bytes -= len(data)

        # Write new SeekHead + Void
        dst.write(new_sh + new_void)
        written += len(new_sh) + len(new_void)

        # Skip old SeekHead + Void in source
        src.seek(sh_offset + sh_total + void_total)

        # Copy gap between old Void end and insertion point
        remaining_bytes = insertion_offset - (sh_offset + sh_total + void_total)
        while remaining_bytes > 0:
            data = src.read(min(chunk_size, remaining_bytes))
            if not data: break
            dst.write(data); written += len(data)
            remaining_bytes -= len(data)

        # Insert Chapters (+ Attachments)
        dst.write(insert_ebml)
        written += len(insert_ebml)
        if verbose:
            print(f"  Inserted {len(chapters_ebml):,}B Chapters"
                  + (f" + {len(attachments_ebml):,}B Attachments" if attachments_ebml else ""))

        # Copy remainder
        last_pct = -1
        while True:
            data = src.read(chunk_size)
            if not data: break
            dst.write(data); written += len(data)
            if verbose:
                pct = int(src.tell() / source_size * 100)
                if pct != last_pct:
                    print(f"  Progress: {pct}%\r", end="", flush=True)
                    last_pct = pct

    if verbose: print(f"\n  Done. {written:,} bytes written.")

    fix_segment_size(out_path)
    if verbose: print(f"  Segment size fixed.")

    if verbose: print(f"\nPatching Cues element...")
    insertion_rel = insertion_offset - seg_body_start
    patch_cues(out_path, seg_body_start, insertion_rel, insert_size)
