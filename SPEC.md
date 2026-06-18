# iMKV Specification
## Interactive Matroska — Format Specification v0.1 (DRAFT)

---

## 1. Overview

iMKV is an extension of the Matroska (MKV) container format for encoding
interactive branching video. It uses Matroska's existing ordered chapter
and chapter script facilities to store branching logic, and extends the
chapter script language with primitives for presenting choices to the
viewer and navigating between branches.

An iMKV file is a valid MKV file and plays correctly in any MKV-capable
player. Players without iMKV support will play the default branch
(determined by chapter script default values) without interaction.

### Design principles

- **Author control over presentation.** The visual design of choice
  menus is as much a part of the work as the video and audio. The format
  preserves authorial intent rather than delegating presentation entirely
  to the player.

- **Semantic data is always present.** Every choice has a human-readable
  text label regardless of how it is displayed. This supports
  accessibility, fallback rendering, and player-side logging.

- **Graceful degradation.** Unknown style values, missing attachments,
  and unrecognized parameters cause the player to fall back to default
  rendering rather than failing.

- **Player agnosticism.** The format does not require any specific
  rendering library. Players may implement rendering using whatever
  facilities are available, provided they respect the semantic structure.

---

## 2. Container Structure

An iMKV file uses Matroska ordered editions. All chapters exist within
a single ordered edition. The virtual timeline defined by the ordered
edition determines playback order; chapter scripts control branching.

### 2.1 Segments

Each distinct scene or segment of the work occupies one or more chapters
within the ordered edition. Chapters are contiguous; the player advances
through them in virtual timeline order unless a script redirects playback.

### 2.2 Attachments

iMKV files may include file attachments in the standard Matroska
`Attachments` element. Attachments are referenced by index (1-based)
from chapter scripts using the `attach(N)` syntax.

Attachment conventions:

- **Attachment 1** should be a 1×1 transparent PNG. This prevents
  players from using an interactive menu image as the file's poster/thumbnail.
- Subsequent attachments may include fonts, images, and other assets
  required for menu rendering.
- Fonts used by menu rendering should be attached in OpenType (.otf)
  or TrueType (.ttf) format.

### 2.3 State Variables

Global state is stored in Matroska chapter script variables. By
convention, iMKV uses the following variable naming scheme:

- `p_` prefix: persistent viewer state (choices made, branches visited)
- Variables are integers; boolean state is represented as 0/1

---

## 3. Chapter Script Language

iMKV extends the Matroska chapter script language with the following
primitives. Scripts are stored in `ChapterProcess` elements with
`ChapterProcessCodecID = 0` (Matroska scripting).

### 3.1 Script Structure

Every script begins with `entry: { ... }` and contains one or more
statements. Scripts are UTF-8 encoded.

```
entry: {
    <statement>;
    <statement>;
}
```

Scripts are attached to chapters with a `ChapterProcessTime` value of:
- `1` — Enter script (fires when the chapter is entered)
- `2` — Leave script (fires when the chapter's end time is reached)

### 3.2 Control Flow

#### Let
```
Let(variable, value);
```
Assigns an integer value to a state variable.

#### If
```
if (condition) {
    <statements>
}
```
Standard conditional. Conditions support `==`, `!=`, `<`, `>`, `<=`,
`>=`, `&&`, `||`, `!`.

#### GotoAndPlay
```
GotoAndPlay(chapter_uid);
```
Seeks to the chapter with the given UID and begins playback. Used within
`Option()` to define branch destinations.

### 3.3 SetFont

```
SetFont(attach(N));
```

Sets the font used for menu text rendering to the font file at attachment
index N. Applies to all subsequent `Menu()` calls until changed.

---

### 3.4 SetTimerBar

```
SetTimerBar(
    x: <percentage>,
    y: <percentage>,
    width: <percentage>,
    height: <percentage>,
    min_percentage: <0.0–1.0>,
    steps: <integer>,
    background: <libass-markup | none>,
    fill: <libass-markup>,
);
```

Sets the default timer bar appearance for all subsequent `Menu()` calls
until changed. Parameters are identical to the `timer_bar` property
described in §4.5.

Any `Menu()` that includes an explicit `timer_bar` parameter overrides
the `SetTimerBar` state for that call only. All other menus inherit the
last `SetTimerBar` state.

`SetTimerBar(none)` disables the timer bar for all subsequent menus.

Typically called once in the enter script of the first chapter:

```
entry: {
    SetFont(attach(2));
    SetTimerBar(
        x: 50%, y: 93.5%,
        width: 100%, height: 2%,
        min_percentage: 0,
        steps: 0,
        background: none,
        fill: "{\\c&HFFFFFF&\\p1}m 0 0 l 100 0 100 100 0 100{\\p0}",
    );
}
```

---

## 4. Menu Primitive

The `Menu()` primitive presents a choice to the viewer and dispatches
to the selected branch.

### 4.1 Syntax

```
Menu(
    timeout: <seconds>,
    default: <1-based index>,
    style: <style>,
    selected: <indicator-spec>,
    unselected: <indicator-spec>,
    Option(<option-spec>),
    Option(<option-spec>),
    ...
);
```

### 4.2 Menu Parameters

#### timeout
Integer, seconds. If the viewer makes no selection within this time,
the option at `default` index is automatically selected. A value of 0
means no timeout (wait indefinitely). Required.

#### default
1-based index into the option list. The option selected on timeout.
Required.

#### style
Controls how option content is rendered. One of:

- `none` — Player renders options using its own default style. A `>`
  indicator is used for the selected option. The author has no control
  over visual presentation.
- `libass` — Option content is rendered as text using the libass subtitle
  renderer. Position and sizing are controlled by the option's `x`, `y`,
  and `width` parameters. The `text` label is rendered using the active
  font and any per-option libass markup provided.
- `image` — Option content is a raster image from a file attachment.
  Position and sizing are controlled by the option's `x`, `y`, and
  `width` parameters.

Unknown values for `style` are treated as `none`.

Default: `none`.

#### selected
Specifies the visual indicator rendered at the position of the currently
selected option. See §4.4.

#### unselected
Specifies the visual indicator rendered at the position of each
non-selected option. See §4.4. Optional; if absent, non-selected options
have no indicator.

### 4.3 Option Parameters

```
Option(
    text: <string>,
    image: attach(<N>),
    x: <percentage>,
    y: <percentage>,
    width: <percentage>,
    height: <percentage>,
    GotoAndPlay(<uid>)
)
```

#### text
String. The semantic label for this option. Always present regardless
of `style`. Used for accessibility, fallback rendering, logging, and
timeout display. Required.

#### image
`attach(N)`. Reference to a file attachment by 1-based index. The
attachment is a raster image (PNG or WebP) used as the visual
representation of this option when `style: image`. Optional; if absent
in `image` style, the player falls back to rendering `text`.

#### x, y
Percentage of frame width/height (0.0–100.0). The center point of this
option's bounding box within the video frame. Required when `style` is
`image` or `libass`.

#### width, height
Percentage of frame width/height. The size of this option's bounding
box. Required when `style` is `image` or `libass`.

#### GotoAndPlay
The branch destination if this option is selected. Required.

### 4.4 Indicator Specification

The `selected` and `unselected` parameters describe a visual element
rendered relative to each option's position. The indicator is a separate
layer, independent of the option content itself — it is rendered on top
of or beneath the option visual without replacing it.

```
{ libass: "<ass markup>", x_offset: <pct>, y_offset: <pct> }
{ image: attach(<N>),    x_offset: <pct>, y_offset: <pct> }
none
```

- `libass`: An ASS override tag string describing the indicator's visual
  appearance. Must not contain `\pos` or `\an` tags — placement is
  determined by the option position plus the offset. The player injects
  `\pos` at render time based on the option's `x`/`y` and the offsets.
- `image`: A raster image attachment used as the indicator.
- `x_offset`, `y_offset`: Offset from the option's center point, as
  percentage of frame dimensions. Positive y is downward. Default 0.
- `none`: No indicator. This is the default for `unselected` if omitted.

For `style: none`, the `selected` and `unselected` parameters are
ignored; the player uses `>` and ` ` (space) respectively.

### 4.5 Timer Bar

The `timer_bar` parameter adds a countdown indicator to a specific
`Menu()` call, overriding the current `SetTimerBar` state for that
menu only. When absent, the menu inherits the `SetTimerBar` state
set in the chapter script (see §3.4). If no `SetTimerBar` has been
called and no `timer_bar` is specified, no timer bar is displayed.

```
timer_bar: {
    x: <percentage>,
    y: <percentage>,
    width: <percentage>,
    height: <percentage>,
    min_percentage: <0.0–1.0>,
    steps: <integer>,
    background: <libass-markup | none>,
    fill: <libass-markup>,
}
```

#### x, y
Center point of the timer bar within the video frame, as percentages
of frame width/height. Required.

#### width, height
Dimensions of the timer bar bounding box as frame percentages. Required.

#### min_percentage
The minimum fill level, expressed as a fraction from 0.0 to 1.0. When
the timer reaches zero the fill is reduced to this fraction of its full
width rather than disappearing entirely. Allows for a non-zero end cap
or border to remain visible. Default: `0` (drains completely).

`min_percentage` corresponds to the dark cap areas visible at each end
of the Undertaker-style bar — regions of the background that the fill
never covers. For Bandersnatch-style bars with no caps, use `0`.

#### steps
If greater than zero, the fill drains in discrete equal-width steps
rather than continuously. The fill jumps to each new step position
as time elapses. `steps: 0` means continuous (smooth) animation.
Default: `0`.

#### background
ASS override tag markup for the static background element of the
timer bar — the container, outline, or decorative shape that the
fill sits inside. The player renders this once when the menu appears
and holds it static throughout. Must not contain `\pos` or `\an`.

If `none`, no background element is rendered.

#### fill
ASS override tag markup for the draining fill element. The player
renders this at the same position as `background`, scaling its width
proportionally to the remaining time fraction (clamped to
`min_percentage` at the low end). Must not contain `\pos` or `\an`.

The fill is clipped to `width * current_fraction` of the bounding
box width. The player scales the libass drawing coordinates
accordingly on each update.

#### Fallback for style: none

When `style: none` is in use, the player SHOULD render a simple
solid-color horizontal bar using its own defaults, ignoring the
`background` and `fill` markup. A thin white bar at the bottom of
the choice panel is the recommended default appearance.

#### Examples

##### Bandersnatch-style (thin white bar, no background, full drain)
```
timer_bar: {
    x: 50%, y: 93.5%,
    width: 100%, height: 2%,
    min_percentage: 0,
    steps: 0,
    background: none,
    fill: "{\\c&HFFFFFF&\\p1}m 0 0 l 100 0 100 100 0 100{\\p0}",
}
```

##### Undertaker-style (hexagonal container, purple fill, capped ends)
```
timer_bar: {
    x: 50%, y: 94%,
    width: 85%, height: 2.5%,
    min_percentage: 0.022,
    steps: 0,
    background: "{\\p1\\c&H1A0A1A&\\alpha&HFF&}m 20 0 l 980 0 1000 50 980 100 20 100 0 50{\\p0}",
    fill: "{\\p1\\c&H8B008B&\\alpha&H00&}m 0 0 l 1000 0 1000 100 0 100{\\p0}",
}
```

---

### 4.6 Examples

#### Plain text menu (style: none)
```
Menu(
    timeout: 10, default: 1,
    Option("Sugar Puffs", GotoAndPlay(3218379847)),
    Option("Frosties",    GotoAndPlay(480515083))
);
```

#### Text menu with image underline indicator (Bandersnatch style)
```
Menu(
    timeout: 10, default: 1,
    style: libass,
    selected: {
        image: attach(2),
        x_offset: 0%, y_offset: 6%
    },
    Option(
        text: "Sugar Puffs",
        x: 25%, y: 88%, width: 40%, height: 8%,
        GotoAndPlay(3218379847)
    ),
    Option(
        text: "Frosties",
        x: 75%, y: 88%, width: 40%, height: 8%,
        GotoAndPlay(480515083)
    )
);
```

#### Text menu with libass pill indicators (Undertaker style)
```
Menu(
    timeout: 10, default: 1,
    style: libass,
    selected: {
        libass: "{\p1\c&H8B008B&\alpha&H40&}m 0 0 b 20 0 20 0 20 20 ...",
        x_offset: 0%, y_offset: 0%
    },
    unselected: {
        libass: "{\p1\c&H333333&\alpha&H80&}m 0 0 b 20 0 20 0 20 20 ...",
        x_offset: 0%, y_offset: 0%
    },
    Option(
        text: "Follow Whispers",
        x: 20%, y: 85%, width: 25%, height: 8%,
        GotoAndPlay(1111111111)
    ),
    Option(
        text: "Follow Fog",
        x: 50%, y: 85%, width: 25%, height: 8%,
        GotoAndPlay(2222222222)
    ),
    Option(
        text: "Follow Lights",
        x: 80%, y: 85%, width: 25%, height: 8%,
        GotoAndPlay(3333333333)
    )
);
```

#### Image option menu (You vs Wild style)
```
Menu(
    timeout: 10, default: 1,
    style: image,
    selected: {
        image: attach(2),
        x_offset: 0%, y_offset: 6%
    },
    Option(
        text: "Restore Power",
        image: attach(3),
        x: 20%, y: 82%, width: 27%, height: 9%,
        GotoAndPlay(1234567890)
    ),
    Option(
        text: "Call for Help",
        image: attach(4),
        x: 50%, y: 82%, width: 27%, height: 9%,
        GotoAndPlay(9876543210)
    ),
    Option(
        text: "Explore",
        image: attach(5),
        x: 80%, y: 82%, width: 27%, height: 9%,
        GotoAndPlay(1122334455)
    )
);
```

---

## 5. Player Requirements

### 5.1 Required behavior

A conforming iMKV player MUST:

- Parse and execute `Menu()`, `Let()`, `If()`, `GotoAndPlay()`,
  `SetFont()`, and `SetTimerBar()` chapter script primitives.
- Present menu options to the viewer with the `text` label visible or
  audible in some form.
- Accept viewer input selecting an option and dispatch `GotoAndPlay`
  accordingly.
- Respect `timeout` and `default`, dispatching the default option when
  the timeout expires.
- Suppress or disable timeline scrubbing when playing an iMKV file, as
  scrubbing corrupts chapter state.

### 5.2 Recommended behavior

A conforming iMKV player SHOULD:

- Render options at the specified `x`/`y`/`width`/`height` positions.
- Render `selected` and `unselected` indicators as specified.
- Render the `timer_bar` if specified, updating the fill width on each
  frame during menu display.
- Use the `SetFont()` attachment for menu text rendering when available.
- Fall back to `style: none` rendering when `style: libass` markup
  cannot be rendered or when `style: image` attachments are missing.

### 5.3 Graceful degradation

Unknown `style` values, unrecognized parameters, and missing attachments
MUST NOT cause player failure. The player falls back to `style: none`
rendering and continues playback.

---

## 6. Coordinate System

All positional values are expressed as percentages of the video frame
dimensions, not the player window dimensions.

- `x: 0%` is the left edge of the frame; `x: 100%` is the right edge.
- `y: 0%` is the top edge of the frame; `y: 100%` is the bottom edge.
- Percentage values are floating point; authors should use at most two
  decimal places.

For films with encoded letterbox bars (aspect ratios wider than 16:9
encoded into a 16:9 frame), the letterbox bars are part of the frame.
Authors should position menus within the black bar area to avoid
obscuring the picture content.

---

## 7. libass Markup Conventions

When `style: libass` is used, or when an indicator uses `libass:`, the
following conventions apply:

- Markup strings are ASS override tag sequences, not complete ASS scripts.
  The player wraps them in a minimal ASS script envelope.
- Markup strings MUST NOT contain `\pos` or `\an` tags. Placement is
  controlled by the option's `x`/`y` parameters and applied by the player.
- The player injects `\pos(x,y)` computed from the option's percentage
  coordinates and the current frame pixel dimensions before passing to
  libass.
- Indicator markup strings receive `\pos` computed from the option
  position plus the `x_offset`/`y_offset`.
- Vector drawing commands (`\p1` ... `\p0`) use coordinates relative to
  the option's bounding box, not the full frame. The player scales them
  to pixel dimensions based on `width`/`height` percentages.

libass version 0.13 or later is recommended. Players using libass
SHOULD pass markup as a single ASS `Dialogue` event line.

---

## 8. Chapter Properties

### 8.1 reusable

```
reusable: <true | false>
```

A hint to streaming clients indicating whether this segment may be
reached more than once across all possible play paths through the
branching graph. A segment is reusable if it has in-degree greater
than one in the chapter graph — i.e., more than one branch leads to
it.

Default: `false`.

This property has no effect on local playback. For streaming clients
that implement speculative branch buffering (see §9), a `reusable: true`
segment SHOULD be retained in the branch cache after the viewer passes
through it, rather than discarded. This avoids re-fetching segments the
viewer is likely to encounter again — particularly relevant for titles
with loop structures (segments reachable on multiple playthroughs or
from multiple branches).

The bake tool computes `reusable` statically from the chapter graph
and annotates each chapter accordingly. Authors do not need to set this
manually.

---

## 9. Streaming Considerations

iMKV is designed primarily for local playback, where random access to
any segment is fast and seek latency is imperceptible. Remote streaming
of interactive content is a substantially harder problem and is treated
here as future work rather than a current requirement. The properties
and guidance in this section are forward-looking.

### 9.1 Keyframe boundary requirement

All chapter start times in a baked iMKV file MUST coincide with a
video keyframe (IDR frame) boundary. A chapter transition that lands
mid-GOP will produce visual artifacting in all players until the next
keyframe is decoded. For H.264 and H.265 with typical 2-4 second GOP
sizes, this means up to several seconds of visible corruption on every
branch transition.

The bake tool MUST verify keyframe alignment for every chapter start
time and MUST either:
- Reject the input with an error identifying the misaligned chapters, or
- Adjust the chapter start time to the nearest preceding keyframe
  boundary, warning the author of the adjustment.

This requirement applies regardless of delivery mechanism. Even local
playback in VLC will exhibit artifacting without keyframe alignment;
streaming scenarios make this worse because re-seeking is more expensive.

### 9.2 Speculative branch buffering

A streaming client with knowledge of the iMKV chapter graph can
implement speculative branch buffering to hide seek latency at choice
points. The approach:

1. When approaching a `Menu()` choice point, the client identifies the
   N branch destinations (typically 2, occasionally 3).
2. The client begins buffering all N branches simultaneously, interleaved
   in bandwidth allocation. The buffering depth need only cover the
   choice window duration (typically 10-14 seconds) plus a margin.
3. When the viewer makes a selection, the client discards buffers for
   unchosen branches and continues buffering the selected branch linearly.
4. The client signals the choice to the server immediately upon selection,
   not at segment boundary. The server uses this signal to begin
   pre-fetching the segments that follow the chosen branch.
5. For branches with `reusable: true`, the client SHOULD retain the
   buffer rather than discarding it, as the viewer may reach that
   segment again via a different path.

Peak bandwidth overhead is approximately N× during the choice window,
dropping back to 1× immediately after selection. For binary choices on
a typical connection this is acceptable. For 3-option choices the
client may reduce per-branch buffer depth proportionally.

This architecture requires:
- A streaming server that understands the iMKV chapter graph and can
  serve segments non-linearly in response to choice signals.
- A client that manages N parallel segment buffers keyed by chapter UID
  rather than byte offset.
- A low-latency side channel (HTTP POST or WebSocket) for choice signals.

Neither HLS nor DASH natively supports this model. A custom streaming
protocol profile, or a DASH extension using `SupplementalProperty`
elements to encode the chapter graph in the manifest, would be required.
This is explicitly out of scope for the current format version.

### 9.3 Segment caching

A streaming client implementing branch buffering SHOULD maintain a
segment cache keyed by chapter UID. When a branch transition targets
a chapter UID already present in the cache, the client SHOULD use the
cached segment without re-fetching. This is particularly valuable for
titles with loop structures where the viewer repeatedly encounters
the same choice points across multiple playthroughs.

The `reusable: true` property (§8.1) is the signal that a given
segment is worth retaining in this cache.

### 9.4 FFmpeg

FFmpeg is a target for future iMKV awareness, independently of any
streaming protocol work. A conforming FFmpeg integration SHOULD:

- Display iMKV chapter script metadata in `ffprobe` output (currently
  silently discarded as unknown `ChapterProcessData` codec payloads).
- Support dumping iMKV scripts to a sidecar format and re-importing
  them, enabling round-trip transcoding without losing interactive
  structure.
- Enforce keyframe boundary alignment (§9.1) when transcoding iMKV
  source files.

---

## 10. Versioning and Extensibility

The iMKV format is versioned via a Matroska tag on the file (specific
tag element TBD). Players encountering a version they do not recognize
SHOULD attempt playback with degraded interactivity rather than refusing
to play.

Parameters not recognized by the player are silently ignored. This
allows future extensions to the `Menu()` syntax without breaking existing
players.

---

## Appendix A: Netflix JSON Mapping

The following table maps Netflix interactive manifest fields to iMKV
equivalents, for reference when authoring conversion tools.

| Netflix field | iMKV equivalent |
|---|---|
| `choice.text` | `Option(text: ...)` |
| `choice.icon.visualStates.default.image.url` | `Option(image: attach(N))` |
| `layout.choiceDisplayTime` | `Menu(timeout: ...)` |
| Layout position percentages | `Option(x:, y:, width:, height:)` |
| Selected state visual | `Menu(selected: ...)` |
| Unselected state visual | `Menu(unselected: ...)` |
| `choice.segmentId` → segment start time | `GotoAndPlay(chapter_uid)` |
| `HorizontalTimer` element | `Menu(timer_bar: {...})` or `SetTimerBar(...)` |
| `timer.minPercentage` | `timer_bar.min_percentage` |
| `timer.progressSteps` | `timer_bar.steps` |
| `timerBackground` image | `timer_bar.background` (libass equivalent) |
| `timerFill` image | `timer_bar.fill` (libass equivalent) |

Netflix manifests use two distinct schema versions across the catalog.
Titles produced from approximately 2020 onward use a `uiDefinition` /
`momentsBySegment` schema with hashed element IDs. Earlier titles
(including Bandersnatch) use a `commonMetadata.layouts` schema with
named layout objects. Both schemas encode the same semantic information
and map to the same iMKV primitives.

---

## Appendix B: Historical Context

The interactive branching film predates digital media by decades.
The first known example is *Kinoautomat* (1967, dir. Radúz Činčera,
Czechoslovakia), in which an actor paused the film to poll the audience
verbally; a projectionist switched reels based on the result. The iMKV
`Menu()` primitive maps directly onto this interaction model despite the
radically different delivery mechanism.

The first commercially released interactive theatrical film in the United
States was *I'm Your Man* (1992, Interfilm), which used audience joystick
systems to aggregate votes. *Mr. Payback: An Interactive Movie* (1995,
Interfilm) followed; it is presumed lost, with no known surviving copies.

Netflix's interactive streaming productions (2017–2022) represent the
most recent large-scale deployment of the form, producing approximately
30 titles across multiple genres. iMKV draws its primary reference
implementation from *Black Mirror: Bandersnatch* (2018).
