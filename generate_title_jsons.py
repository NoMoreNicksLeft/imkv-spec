#!/usr/bin/env python3
"""
generate_title_jsons.py — produce iMKV title JSON skeletons from Netflix manifests.
"""

import json, os, glob, re, random, sys
sys.path.insert(0, os.path.dirname(__file__))

BASE       = os.path.join(os.path.dirname(__file__), "netflix_json")
OUT_DIR    = os.path.join(os.path.dirname(__file__), "titles")
SCHEMA_VER = 1
os.makedirs(OUT_DIR, exist_ok=True)

def ms_to_tc(ms):
    ms = int(ms)
    h = ms // 3_600_000; ms %= 3_600_000
    m = ms // 60_000;    ms %= 60_000
    s = ms // 1_000;     ms %= 1_000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

STRING_ENUMS = {
    "p_ps": {"n":0,"b":1,"f":2,"t":3},
    "p_pc": {"n":0,"o":1,"t":2},
    "p_vs": {"n":0,"c":1,"k":2,"t":3},
}

def s2i(var, val):
    return STRING_ENUMS.get(var, {}).get(val, 0)

def xlate_pre(cond):
    if not cond: return "1"
    op = cond[0]
    if op == "persistentState": return f"{cond[1]} != 0"
    if op == "not":
        inner = cond[1] if len(cond)==2 else ["and"]+list(cond[1:])
        return f"!({xlate_pre(inner)})"
    if op == "and": return " && ".join(f"({xlate_pre(c)})" for c in cond[1:])
    if op == "or":  return " || ".join(f"({xlate_pre(c)})" for c in cond[1:])
    if op == "eql":
        lc, right = cond[1], cond[2]
        if lc[0] == "persistentState":
            var = lc[1]
            if isinstance(right, bool): return f"{var} == {'1' if right else '0'}"
            if isinstance(right, str):  return f"{var} == {s2i(var,right)}"
            return f"{var} == {right}"
        return f"{xlate_pre(lc)} == {right}"
    return "1"

def state_lets(d):
    lines = []
    for var, val in d.items():
        if isinstance(val, bool): lines.append(f"    Let({var}, {'1' if val else '0'});")
        elif isinstance(val, str): lines.append(f"    Let({var}, {s2i(var,val)});")
        elif isinstance(val, (int,float)): lines.append(f"    Let({var}, {int(val)});")
    return lines

def build_enter(moments):
    lines = []
    for m in moments:
        if m.get("type") != "notification:playbackImpression": continue
        persistent = m.get("impressionData",{}).get("data",{}).get("persistent",{})
        if not persistent: continue
        pre = m.get("precondition",[])
        lets = state_lets(persistent)
        if pre:
            lines.append(f"    if ({xlate_pre(pre)}) {{")
            lines += [f"    {l}" for l in lets]
            lines.append("    }")
        else:
            lines += lets
    if not lines: return None
    return "entry: {\n" + "\n".join(lines) + "\n}"

def build_menu(choice_moment, uid_map, preconditions, segmentGroups, timeout_s):
    choices     = choice_moment.get("choices", [])
    default_idx = choice_moment.get("defaultChoiceIndex", 0) + 1
    options = []
    for i, choice in enumerate(choices, 1):
        text = choice.get("text", f"Option {i}").title().replace('"', "'")
        opt  = {"text": text}

        # Image
        img_url = (choice.get("icon",{})
                         .get("visualStates",{})
                         .get("default",{})
                         .get("image",{})
                         .get("url",""))
        if not img_url:
            bg = choice.get("image",{}).get("styles",{}).get("backgroundImage","")
            if bg: img_url = re.sub(r'^url\(|\)$', '', bg)
        if img_url:
            opt["image"] = {"attach": img_url.split("/")[-1]}
            opt["_image_url"] = img_url

        cimp = choice.get("impressionData",{}).get("data",{}).get("persistent",{})
        if cimp: opt["_state_on_select"] = cimp

        if "segmentId" in choice:
            target = choice["segmentId"]
            opt["goto"] = target if target in uid_map else 0
            if target not in uid_map: opt["_unresolved"] = target
        elif "sg" in choice:
            sg_name = choice["sg"]
            group   = segmentGroups.get(sg_name, [])
            cases = []
            for item in group:
                if isinstance(item, str):
                    pre = preconditions.get(item, [])
                    cases.append({"condition": xlate_pre(pre), "segment": item})
                elif isinstance(item, dict):
                    seg = item.get("segment","")
                    pre = preconditions.get(item.get("precondition",""), [])
                    cases.append({"condition": xlate_pre(pre), "segment": seg})
            opt["goto"] = cases[0]["segment"] if cases else 0
            opt["_segment_group"] = sg_name
            opt["_segment_group_cases"] = cases

        options.append(opt)

    return {
        "timeout":   timeout_s,
        "default":   default_idx,
        "style_ref": "default",
        "options":   options,
    }

def build_leave(seg_id, seg_data, moments, uid_map, preconditions, segmentGroups):
    cm = next((m for m in moments
               if m.get("type") in ("scene:cs_bs","scene:cs_template")), None)
    if cm:
        ui_d = cm.get("uiDisplayMS", cm.get("startMs", seg_data.get("endTimeMs",0)))
        ui_h = cm.get("hideTimeoutUiMS", cm.get("uiHideMs",
               cm.get("endMs", ui_d + 10000)))
        t    = max(1, int((ui_h - ui_d) / 1000))
        return {"menu": build_menu(cm, uid_map, preconditions, segmentGroups, t)}
    dn = seg_data.get("defaultNext")
    if dn and dn in uid_map:
        return {"script": f"entry: {{\n    GotoAndPlay({uid_map[dn]}); // -> {dn}\n}}"}
    return None

def load_title(tdir):
    timing_files = sorted([f for f in glob.glob(f"{tdir}/*.json")
                           if 'info' not in os.path.basename(f).lower()
                           and 'default' not in os.path.basename(f).lower()])
    info_files   = sorted(glob.glob(f"{tdir}/*English*info.json") +
                          glob.glob(f"{tdir}/*English*Info.json") +
                          glob.glob(f"{tdir}/*EnglishInfo.json"))
    if not info_files:
        info_files = sorted(glob.glob(f"{tdir}/*info.json") +
                            glob.glob(f"{tdir}/*Info.json"))[:1]

    seg_data_all = {}
    initial_seg  = None
    for tf in timing_files:
        try:
            with open(tf) as f: d = json.load(f)
            if 'segments' in d:
                seg_data_all = d['segments']
                initial_seg  = d.get('initialSegment')
                break
        except: pass

    ivm = None
    for ifile in info_files:
        try:
            with open(ifile) as f: d = json.load(f)
            if 'jsonGraph' in d:
                for vid_id, vdata in d['jsonGraph']['videos'].items():
                    ivm = vdata.get('interactiveVideoMoments',{}).get('value')
                    if ivm: break
            if ivm: break
        except: pass

    if not seg_data_all: return None, "no segment timing data"
    if not ivm:          return None, "no interactiveVideoMoments"

    return (seg_data_all, initial_seg,
            ivm.get('momentsBySegment',{}),
            ivm.get('preconditions',{}),
            ivm.get('segmentGroups',{})), None

def build_json(title_name, seg_data_all, initial_seg,
               moments_by_seg, preconditions, segmentGroups):
    uid_map = {sid: random.randint(1, 2**32) for sid in seg_data_all}
    sorted_segs = sorted(seg_data_all.items(),
                         key=lambda x: int(x[1].get('startTimeMs',0)))
    chapters = []
    image_urls = {}

    for seg_id, seg_data in sorted_segs:
        moments = moments_by_seg.get(seg_id, [])
        enter   = build_enter(moments)
        leave   = build_leave(seg_id, seg_data, moments, uid_map,
                              preconditions, segmentGroups)
        ch = {
            "uid":   uid_map[seg_id],
            "name":  seg_id,
            "start": ms_to_tc(seg_data.get('startTimeMs',0)),
            "end":   ms_to_tc(seg_data.get('endTimeMs',
                     seg_data.get('startTimeMs',0)+1000)),
        }
        if enter: ch["enter"] = enter
        if leave: ch["leave"] = leave
        chapters.append(ch)

        if isinstance(leave, dict) and "menu" in leave:
            for opt in leave["menu"].get("options",[]):
                url = opt.get("_image_url","")
                if url: image_urls[url.split("/")[-1]] = url

    attachments = [
        {"filename":"1x1.png","mime":"image/png",
         "description":"Transparent placeholder (prevents VLC thumbnail)"},
    ]
    for fname, url in sorted(image_urls.items()):
        ext  = os.path.splitext(fname)[1].lower()
        mime = {".png":"image/png",".webp":"image/webp",
                ".jpg":"image/jpeg",".jpeg":"image/jpeg"}.get(ext,"image/webp")
        attachments.append({"filename":fname,"mime":mime,
                             "_source_url":url})

    return {
        "schema_version": SCHEMA_VER,
        "title":          title_name,
        "initial_segment":initial_seg,
        "_note": ("Auto-generated skeleton. Fill in styles/positions before baking. "
                  "Fields prefixed _ are informational and ignored by the bake tool."),
        "attachments": attachments,
        "styles": {
            "default": {
                "style":      "none",
                "selected":   {"type":"none"},
                "unselected": {"type":"none"},
                "_note": "Set style to 'libass' or 'image' and add indicator specs",
            }
        },
        "chapters": chapters,
    }

def safe_fn(name):
    name = name.replace(": "," - ").replace(":"," -")
    name = re.sub(r'[<>"/\\|?*]','',name)
    return re.sub(r'\s+','_',name.strip())

SKIP = set()  # nothing to skip — multi-episode titles handled below
MULTI_EPISODE = {"Battle Kitty", "Trivia Quest", "You vs. Wild"}

def load_moments_as_segments(tdir):
    """For titles where segment timing lives in moments, not a segments file."""
    info_files = sorted(glob.glob(f"{tdir}/*-en.json") +
                        glob.glob(f"{tdir}/*English*info.json") +
                        glob.glob(f"{tdir}/*English*Info.json"))
    if not info_files: return None, "no info file"

    ivm = None
    for ifile in info_files:
        try:
            with open(ifile) as f: d = json.load(f)
            if 'jsonGraph' in d:
                for vid_id, vdata in d['jsonGraph']['videos'].items():
                    ivm = vdata.get('interactiveVideoMoments',{}).get('value')
                    if ivm: break
            if ivm: break
        except: pass

    if not ivm: return None, "no IVM"

    mbs = ivm.get('momentsBySegment', {})
    # Synthesise seg_data_all from moment timings
    seg_data_all = {}
    initial_seg  = None
    for seg_id, moments in mbs.items():
        start_ms = min((m.get('startMs',0) for m in moments), default=0)
        end_ms   = max((m.get('endMs',0)   for m in moments), default=start_ms+1000)
        # Find defaultNext from choices of linear moments (if any)
        choice_m = next((m for m in moments
                         if m.get('type') in ('scene:cs_bs','scene:cs_template')), None)
        default_next = None
        if choice_m:
            choices = choice_m.get('choices',[])
            di = choice_m.get('defaultChoiceIndex',0)
            if choices and di < len(choices):
                default_next = choices[di].get('segmentId')
        seg_data_all[seg_id] = {
            'startTimeMs': start_ms,
            'endTimeMs':   end_ms,
        }
        if default_next:
            seg_data_all[seg_id]['defaultNext'] = default_next
        if initial_seg is None:
            initial_seg = seg_id  # will be overridden below

    # Try to find true initial segment (lowest start time)
    if seg_data_all:
        initial_seg = min(seg_data_all, key=lambda s: seg_data_all[s]['startTimeMs'])

    return (seg_data_all, initial_seg,
            mbs,
            ivm.get('preconditions',{}),
            ivm.get('segmentGroups',{})), None

results = []

def process_one(tdn, tdir, label=None):
    """Process a single title directory. label overrides the output filename prefix."""
    out_label = label or tdn

    data, err = load_title(tdir)
    if err:
        data, err2 = load_moments_as_segments(tdir)
        if err2:
            return (out_label, "ERROR", f"{err} / {err2}")

    seg_data_all, initial_seg, mbs, pre, sg = data
    tj = build_json(out_label, seg_data_all, initial_seg, mbs, pre, sg)

    out = os.path.join(OUT_DIR, safe_fn(out_label)+".json")
    with open(out,'w') as f: json.dump(tj, f, indent=2)

    n_ch  = len(tj['chapters'])
    n_img = len([a for a in tj['attachments']
                 if 'image' in a.get('mime','') and '1x1' not in a['filename']])
    return (out_label, "OK", f"{n_ch} chapters, {n_img} images -> {os.path.basename(out)}")


for tdn in sorted(os.listdir(BASE)):
    tdir = os.path.join(BASE, tdn)
    if not os.path.isdir(tdir): continue

    if tdn in MULTI_EPISODE:
        # Process each episode subfolder separately
        eps = sorted([e for e in os.listdir(tdir)
                      if os.path.isdir(os.path.join(tdir, e))])
        for ep in eps:
            ep_dir   = os.path.join(tdir, ep)
            ep_label = f"{tdn} - {ep}"
            results.append(process_one(tdn, ep_dir, ep_label))
        continue

    if tdn in SKIP:
        results.append((tdn, "SKIP", "no JSON available"))
        continue

    results.append(process_one(tdn, tdir))

print("\n=== Results ===")
for name, status, detail in results:
    marker = "✓" if status=="OK" else ("·" if status=="SKIP" else "✗")
    print(f"  {marker} {name[:50]:<50} {detail}")
print(f"\nOutput directory: {OUT_DIR}")
print(f"Files written: {sum(1 for _,s,_ in results if s=='OK')}")
