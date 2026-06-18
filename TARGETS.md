# iMKV Format — Known Interactive Video Works

This document catalogs known interactive video works that are candidates
for conversion to or authoring in the iMKV format. It is maintained here
temporarily and will migrate to the `imkv-spec` repository when that is
established.

---

## Netflix Interactive (via Eveep23/Interactive-Player compatibility list)

The following titles were produced by Netflix using their proprietary
interactive format. Conversion to iMKV requires the source video and the
corresponding interactive manifest JSON, which encodes branching logic,
segment boundaries, choice point timing, and state variables.

Black Mirror: Bandersnatch is the primary reference implementation for
the iMKV format and the VLC chapter script engine.

- Black Mirror: Bandersnatch *(primary reference implementation)*
- Minecraft Story Mode (Episodes 1-5)
- Cat Burglar
- Buddy Thunderstruck: The Maybe Pile
- Headspace: Unwind Your Mind
- Escape the Undertaker
- Carmen Sandiego: To Steal or Not to Steal
- Barbie: Epic Road Trip
- Puss in Book: Trapped in an Epic Tale
- Stretch Armstrong: The Breakout
- Johnny Test's Ultimate Meatloaf Quest
- Spirit Riding Free: Ride Along Adventure
- The Last Kids on Earth: Happy Apocalypse to You
- Unbreakable Kimmy Schmidt: Kimmy vs. the Reverend
- Captain Underpants: Epic Choice-O-Rama
- The Boss Baby: Get That Baby
- Trivia Quest (Episodes 1-30)
- Jurassic World Camp Cretaceous: Hidden Adventure
- Animals on the Loose: A You vs Wild Movie
- You vs Wild: Out Cold
- Ranveer vs Wild with Bear Grylls
- You vs Wild (Episodes 1-8)
- We Lost Our Human
- Choose Love
- Battle Kitty (Episodes 1-9)

---

## Theatrical and Physical Media

These works predate streaming interactive formats. Conversion to iMKV
requires physical media acquisition, ripping, and reconstruction of the
branching logic from the original release format.

### I'm Your Man (1992, Interfilm)
- Status: Procurable. DVD release 1998, in hand.
- Original format: Theatrical with Interfilm joystick system (audience
  aggregate voting). Home release approximates this via DVD menu navigation.
  The disc is a hybrid DVD-ROM: the VIDEO_TS side provides a simplified
  interactive experience via DVD menus; the DVD-ROM partition contains a
  Macromedia Director projector (YOURMAN.DXR) and 30 AVI files encoding
  the full branching structure for PC playback. The PC version is the more
  complete interactive experience.
- Branching structure (from Director script analysis):
  - Opening: choose one of three men (Leslie / Jack / Richard) → their
    montage (01LesM / 02JackM / 03RichM)
  - Party scene: character-dependent (04PaLes / 05PaJack / 06PaRich)
  - After party choice → GoPaLes / GoPaJack / GoPaRich
  - 07FBI → 08Jack
  - Choice: Leslie (09) or Babes (10)
  - 11KillLe or 12Romanc
  - Choice: Roof (14) or BackPa (15) → 16Run → 17Jump → 18Agent → 25RunaWa
  - Choice: GoodGi (19) or BadGi (20)
  - Endings: 29LesEnd / 30JacEnd / 31RicEnd (character-dependent)
  - Additional segments: 21GGEnd, 22Hall, 23BedRoo, 24LowJa, 27LowRi
  - Note: segment 26 absent from AVI list; director's cut segments present
- Conversion path: Extract VOB segments from ISO, transcode to H.264/HEVC,
  map Director branching graph to iMKV title JSON, bake. Many choice points
  use image options (two options, both images) rather than text — iMKV
  image-style menus apply directly.
- Notes: First commercially released interactive theatrical film in the
  United States. Historically significant. The 1992 film was released on
  DVD in 1998.

### Mr. Payback: An Interactive Movie (1995, Interfilm)
- Status: Presumed lost. Laserdisc only, production run of approximately
  50 copies. None have surfaced publicly.
- Original format: Theatrical with Interfilm joystick system. No known
  home release with branching intact.
- Conversion path: If a Laserdisc copy surfaces: acquire, rip via
  Domesday Duplicator, decode RF to composite, reconstruct branching from
  disc chapter/angle structure.
- Notes: If preserved, would represent a significant archival achievement.
  The interactive logic would need to be reconstructed from the disc
  structure as no manifest data is known to exist.

### Kinoautomat (1967, dir. Radúz Činčera, Czechoslovakia)
- Status: Interactive DVD version exists. Chris Hales (researcher, University
  of the Arts London) undertook what he described as "considerable archaeology"
  to produce an interactive DVD from the original 35mm materials, completed
  circa 2005. A restored version has been screened theatrically in Prague with
  audience voting hardware. A screener (believed to be the complete 63-minute
  film) has reportedly been made available digitally by an institute, identity
  unknown.
- Original format: Theatrical. An actor (Miroslav Horníček) paused the film
  at nine choice points and polled the audience verbally; branching was
  executed by the projectionist switching reels. Audience voting via colored
  buttons on armrests.
- Running time: 63 minutes. Nine choice points, binary choices, single
  converging ending. Total footage estimated 75-80 minutes including alternate
  branches. Branching is deliberately convergent — no matter what the audience
  votes, the film reaches the same ending. This is an intentional philosophical
  statement about free will and determinism.
- Conversion path: Obtain the Hales interactive DVD or the digital screener.
  Reconstruct branching from DVD IFO structure or documented story structure.
  Author iMKV chapter scripts. Nine Menu() calls, each binary.
- Notes: First known interactive film in history. Banned by Communist
  censors in Czechoslovakia in 1972 as politically unconfident. Restored by
  Činčera's daughter Alena Cincerova in 2006. Cited in SPEC.md appendix as
  the origin of the form. All major Hollywood studios attempted to license
  the format in the late 1960s but were blocked by Socialist state ownership.
  Script by Pavel Juráček.

### Switching (2003, dir. Morten Schjødt, Denmark)
- Status: DVD release. Distributed by SF Film A/S (Denmark). Financed by
  the Danish Film Institute with EU MEDIA Programme support. Procurable.
- Original format: DVD-native interactive film. Designed specifically for
  DVD rather than theatrical. The interactivity model is non-standard:
  the viewer can change the film at any time, jumping between time and
  location freely. The interface is transparent — there are no on-screen
  buttons; the film itself is the clickable object.
- Conversion path: Acquire DVD. Rip and examine IFO structure to reconstruct
  branching logic. Note: the non-linear, viewer-initiated model may not map
  cleanly onto iMKV's Menu() primitive, which assumes timed discrete choice
  points. Assess feasibility after examining disc structure.
- Notes: Described as the first Danish interactive film. Danish Film Institute
  institutional backing makes this well-preserved and likely procurable via
  the DFI or Danish library system. The interaction model is more
  experimental than narrative-choice — may be at the edge of iMKV's scope.

### Cause and Effect (2010, dir. Chris Hales, UK)
- Status: Live performance work, not a retail release. Chris Hales presents
  this as an interactive cinema performance in which the audience interacts
  with multiple short films. Related to his Kinoautomat DVD restoration work.
- Original format: Live performance / installation.
- Conversion path: Not a straightforward candidate. Documented here for
  completeness and because Hales's academic work on interactive cinema
  ("Cinematic Interaction: From Kinoautomat to Cause and Effect", Digital
  Creativity, 2005) is a primary reference for the historical context.
- Notes: Hales also created Jinx (1996), a touchscreen installation, and
  Natural History (2003) and Crescendo (2003), audience-participation shorts.

---

## Other

### YouTube Interactive Videos
- Status: Various. YouTube's native interactive format uses end-screens
  and cards, which are not directly convertible.
- Conversion path: TBD. Would require reconstructing the branching
  logic from the video structure and authoring new iMKV chapter scripts.

### Corporate Training Video Genre
- Status: Largely inaccessible. The overwhelming majority of interactive
  corporate training content is proprietary, held in internal LMS systems
  (Cornerstone, SAP SuccessFactors, Workday Learning), or distributed via
  closed SCORM/xAPI packages that embed video rather than using open
  container formats. Studios that produced this content (Cine-Med, McGraw-
  Hill, Encyclopædia Britannica's corporate division, innumerable smaller
  producers) either no longer exist or hold rights tightly.
- Format notes: Most DVD-era corporate interactive training was authored in
  Authorware, Director/Shockwave, or proprietary DVD authoring tools. The
  branching logic is typically encoded in the authoring tool's project files
  rather than anything extractable from the video container. Post-DVD, the
  dominant format is SCORM, which is HTML/JavaScript wrapping video — the
  branching is in JavaScript, not in the video file.
- Practical obstacles beyond access: The content itself is typically
  jurisdiction-specific, organization-specific, and ages quickly (compliance
  requirements, product versions, org charts). A 1998 sexual harassment
  training video for a specific company is of marginal general interest and
  its branching structure is unlikely to represent anything not covered by the
  Netflix catalog. The embarrassment concern is real but secondary — the
  primary issue is that there is no archive, no manifest, and no known path
  to bulk access.
- Exceptions worth noting: Some publicly-funded training content (US federal
  agencies, military, some state governments) is technically FOIA-accessible
  and occasionally surfaces on the Internet Archive. The US Army and Air Force
  produced extensive interactive training video on LaserDisc and CD-ROM in the
  1980s-90s that would be historically interesting. Defense Technical
  Information Center (DTIC) holds some of this.
- Verdict: Low priority for iMKV conversion. The format should be capable
  of encoding typical training branching (scenario choices, consequence
  branches, knowledge check gates) — that capability falls out naturally from
  the existing Menu() and GotoAndPlay() primitives. No active acquisition
  effort warranted.

---

## Notes on Scope

The iMKV format is intended to be agnostic to the original delivery
mechanism and input method. Whether choices were made by a single viewer
pressing a key, a theater audience voting with joysticks, a show of
hands, or a corporate trainer clicking a mouse -- all produce the same
signal at the format level: an option was selected. The file format does
not encode the input mechanism, only the branching structure and
presentation.

There is no maximum number of options per choice point. Authors are
responsible for ensuring their choice presentations are legible given
their chosen layout and placement parameters.

---

## Tooling Notes

### Bake tool: keyframe boundary enforcement
All chapter boundaries in a baked iMKV file must land on keyframe (IDR
frame) boundaries in the video stream. This is a hard requirement, not a
best-effort goal. A chapter jump that lands mid-GOP will produce visual
artifacting in all players until the next keyframe is decoded (typically
1-4 seconds depending on GOP size). The bake tool must verify keyframe
alignment for every chapter start time and either reject misaligned
chapters or adjust them to the nearest preceding keyframe. This applies
equally to local playback and any future streaming use case.

### FFmpeg
FFmpeg is a target for future iMKV awareness, independently of any
streaming protocol work. Minimum desirable behavior:
- `ffprobe` should display iMKV chapter script metadata (currently
  silently discarded as unknown ChapterProcessData codec)
- `ffmpeg` should be able to dump iMKV scripts to a sidecar format
  and re-import them, enabling round-trip transcoding without losing
  interactive structure
- Longer term: FFmpeg understanding of the chapter graph would enable
  tools built on FFmpeg to be iMKV-aware without custom patches

This is a contribution target for when the format stabilizes.

### Streaming protocols: assessment
iMKV is a local playback format. Extending it to remote streaming is a
separate and substantially harder problem. Key findings:

HLS and DASH are not suitable transports for interactive branching
content. HLS allows custom `#EXT-X-` tags but is a pull protocol with
no model for branching; DASH's MPD manifest is static. Neither protocol
can represent a content graph without fundamental architectural changes.
Even if the protocols were extended, the server-side toolchain (FFmpeg
generating HLS segments, Plex Media Server packaging them) has no model
for a directed content graph and would require replacement, not extension.
Plex Inc. specifically is not a viable partner for this — they are
pursuing a commercial streaming strategy and have consistently
deprioritized self-hosting infrastructure improvements.

The Netflix approach (bespoke stateful API returning next-segment URLs
based on choice signals, with all branches pre-encoded on CDN) is the
only working large-scale solution, and it is not an open protocol.

Direct play over a local network (SMB/NFS mount, or Plex direct play on
LAN) is workable because seeking is fast enough that branch jumps are
imperceptible, and keyframe-aligned chapters eliminate codec artifacting.
Remote direct play introduces seek latency and potential buffering issues
(the player buffers the wrong branch ahead of a choice point).

mpv is the next target player implementation after VLC. mpv is the
underlying engine in Plex HTPC among other clients, making it the
highest-leverage target for local playback use cases. The chapter script
engine and OSD rendering would need to be ported or reimplemented as an
mpv plugin.

**Conclusion:** iMKV solves local playback correctly. Remote streaming of
interactive content is a distinct problem requiring server-side
intelligence that no existing open infrastructure provides. These should
not be conflated. A third streaming protocol without industry backing is
not viable. The correct position is: make local playback excellent, make
FFmpeg aware, pursue mpv, and treat streaming as a future unsolved
problem rather than a current blocker.
