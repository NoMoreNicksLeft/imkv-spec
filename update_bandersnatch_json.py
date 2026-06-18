#!/usr/bin/env python3
"""
update_bandersnatch_json.py

Updates the Bandersnatch title JSON with:
- Correct attachments (font + underline image)
- Presentation style (libass, Netflix Sans font, underline indicator)
- SetFont and SetTimerBar in first chapter enter script
- x/y/width/height on every menu option using exact Netflix layout data
- Timer bar spec derived from Netflix manifest
"""

import json, re, os

PATH = os.path.expanduser(
    "~/Projects/imkv-spec/titles/Black_Mirror__Bandersnatch.json")

with open(PATH) as f:
    title = json.load(f)

# ── Attachments ────────────────────────────────────────────────────────────
# Order matters: 1x1.png first, then font, then images
title['title'] = "Black Mirror: Bandersnatch"
title['attachments'] = [
    {
        "filename": "1x1.png",
        "mime": "image/png",
        "description": "Transparent placeholder (prevents VLC thumbnail)"
    },
    {
        "filename": "NetflixSans-Regular.otf",
        "mime": "font/otf",
        "description": "Netflix Sans Regular — menu OSD font",
        "path": "../../assets/fonts/NetflixSans-Regular.otf"
    },
    {
        "filename": "choice_point_underline_2x.png",
        "mime": "image/png",
        "description": "Underline selection indicator",
        "_source_url": "https://assets.nflxext.com/ffe/oui/interactive/bs/choicepoint/web/20181116/choice_point_underline_2x.png"
    },
    {
        "filename": "netflix_2x.png",
        "mime": "image/png",
        "description": "Netflix choice point image",
        "_source_url": "https://assets.nflxext.com/ffe/oui/interactive/bs/choicepoint/web/20181116/netflix_2x.png"
    },
    {
        "filename": "pacs_2x_update.png",
        "mime": "image/png",
        "description": "PACS choice point image",
        "_source_url": "https://assets.nflxext.com/ffe/oui/interactive/bs/choicepoint/web/20181116/pacs_2x_update.png"
    },
    {
        "filename": "whitebear_2x.png",
        "mime": "image/png",
        "description": "White Bear choice point image",
        "_source_url": "https://assets.nflxext.com/ffe/oui/interactive/bs/choicepoint/web/20181116/whitebear_2x.png"
    },
]

# ── Styles ─────────────────────────────────────────────────────────────────
# Bandersnatch layout from Netflix manifest:
#   Choice 1: left=7.34%, width=42.66% → center_x=28.67%, top=85.56%, height=5.21% → center_y=88.16%
#   Choice 2: right=7.34%, width=42.66% → center_x=71.33%, same y
#   Underline: bottom-center of choice slot, width=30% of slot
#     → width = 42.66*0.30 = 12.80% of frame
#     → x_offset=0 (centered on option), y_offset=+3% (just below text baseline)
#   Timer: white bar, 100% frame width, height=0.4% of frame (2% of 20% container)
#     Container bottom=0 of frame, timer top=0 of container → y=80%
#     We render at y=86.0% to push the bar down into the bottom letterbox
#     band rather than sitting over picture content (per user feedback;
#     original Netflix-derived value was y=80.2%)

title['styles'] = {
    "default": {
        "style": "libass",
        "selected": {
            "type": "image",
            "attach": "choice_point_underline_2x.png",
            "x_offset": 0,
            "y_offset": 3
        },
        "unselected": {
            "type": "none"
        },
        "_note": (
            "Netflix Sans font renders text in uppercase with letterSpacing 0.05em. "
            "dimOnIdle: unselected option dims — implemented via unselected opacity "
            "in the renderer. Underline is the Netflix choice_point_underline image, "
            "centered below the text at y_offset +3%."
        )
    }
}

# ── Option positions ───────────────────────────────────────────────────────
# From Netflix manifest layout l2 (used by most 2-choice menus):
#   c_1: left=7.34%, width=42.66%, top=85.56%, height=5.21%
#        center_x = 7.34 + 42.66/2 = 28.67
#        center_y = 85.56 + 5.21/2 = 88.16
#   c_2: right=7.34%, width=42.66%, top=85.56%, height=5.21%
#        center_x = (100-7.34) - 42.66/2 = 71.33
#        center_y = 88.16

# 3-choice layout (l3): need to check manifest for those
# For now use evenly-spaced fallback: 21%, 50%, 79%
# 4-choice layout: 15%, 38%, 62%, 85%

def option_positions(n):
    """Return list of (center_x, center_y, width, height) for n options."""
    # y history: 88.16% (Netflix-derived) → 94.0% → 96.0% → 94.5%. Pulled
    # back up slightly from 96.0% to leave more clearance above the text's
    # actual rendered ink for the timer bar, which was colliding with
    # picture content despite sitting numerically below the text's anchor
    # point — the glyphs render taller than font_size/2 suggested. Tuned
    # by trial-and-error against real screenshots, not a fixed formula.
    y      = 94.5
    height = 5.21
    if n == 2:
        return [
            (28.67, y, 42.66, height),
            (71.33, y, 42.66, height),
        ]
    elif n == 3:
        # Three equal slots across the frame
        return [
            (16.67, y, 28.0, height),
            (50.0,  y, 28.0, height),
            (83.33, y, 28.0, height),
        ]
    else:
        # Generic: evenly spaced
        slot_w = 85.0 / n
        margin = (100.0 - 85.0) / 2
        return [
            (margin + slot_w * i + slot_w / 2, y, slot_w * 0.9, height)
            for i in range(n)
        ]

# ── Chapters: add positions + SetFont/SetTimerBar to first enter ───────────

TIMER_BAR = {
    "x": 50,
    "y": 88.0,
    "width": 100,
    "height": 0.4,
    "min_percentage": 0,
    "steps": 0,
    "background": "none",
    "fill": "{\\c&HFFFFFF&\\p1}m 0 0 l 1000 0 1000 1000 0 1000{\\p0}",
    "_note": (
        "White bar, full frame width, 0.4% height (= 2% of 20% container). "
        "Positioned at y=88.0% (history: 80.2% → 86.0% → 90.0% → 88.0%) — "
        "pulled back up from 90.0% because it was sitting on/over picture "
        "content despite being numerically below the text row; the option "
        "text's rendered glyph height eats into the gap more than expected. "
        "Tuned by trial-and-error against real screenshots."
    )
}

first_chapter = True

for ch in title['chapters']:
    # Inject SetFont + SetTimerBar into the first chapter's enter script
    if first_chapter:
        enter = ch.get('enter', '')
        if not enter:
            enter = 'entry: {\n}'
        # Insert after opening brace
        inject = (
            '    SetFont(attach(2)); // NetflixSans-Regular.otf\n'
            '    SetTimerBar(\n'
            '        x: 50%, y: 88.0%,\n'
            '        width: 100%, height: 0.4%,\n'
            '        min_percentage: 0,\n'
            '        steps: 0,\n'
            '        background: none,\n'
            '        fill: "{\\c&HFFFFFF&\\p1}m 0 0 l 1000 0 1000 1000 0 1000{\\p0}",\n'
            '    );\n'
        )
        ch['enter'] = enter.replace('entry: {\n', 'entry: {\n' + inject, 1)
        first_chapter = False

    # Add positions to menu options
    leave = ch.get('leave')
    if not isinstance(leave, dict) or 'menu' not in leave:
        continue

    menu = leave['menu']
    options = menu.get('options', [])
    n = len(options)
    positions = option_positions(n)

    for i, opt in enumerate(options):
        cx, cy, w, h = positions[i]
        opt['x']      = round(cx, 2)
        opt['y']      = round(cy, 2)
        opt['width']  = round(w,  2)
        opt['height'] = round(h,  2)

    # Detect image menus: if every option has an image, use style: image
    all_have_images = all(opt.get('image') for opt in options)
    if all_have_images:
        menu['style'] = 'image'
    else:
        # Update style_ref
        menu['style_ref'] = 'default'

    # Add timer_bar only if this menu overrides the global default
    # (Bandersnatch uses uniform timer, so we don't override per-menu)

with open(PATH, 'w') as f:
    json.dump(title, f, indent=2)

print(f"Updated: {PATH}")
print(f"Chapters: {len(title['chapters'])}")
menus = sum(1 for ch in title['chapters']
            if isinstance(ch.get('leave'), dict) and 'menu' in ch['leave'])
print(f"Menus:    {menus}")
print(f"Attachments:")
for a in title['attachments']:
    print(f"  {a['filename']}")
