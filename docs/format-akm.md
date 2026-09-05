# AKM, and how to get a song into it

AKM — Arkos's "minimalist" format — is the successor to AKL: patterns,
instruments and an order list, encoded harder. It is the smallest Arkos
format measured here, 3,654 bytes for Edge Grinder's 349-second tune against
AKL's 4,741, and Targhan's own player header says *"This player may actually
replace Lightweight!"*.

`reference/AKM.md` is the format spec and `reference/PlayerAkm_z80.asm` is
Arkos's Z80 player, both vendored. Read those before this.

`lib/akmplayer.asm` is **the only 6502 AKM player there is**. Arkos ships 6502
players for AKY alone, and only for machines with a real AY.

**What is open is in [`akm-open-questions.md`](akm-open-questions.md)**: a
rendering discrepancy on 25 corpus songs, and the eleven Atari ST and MSX
tunes. Neither blocks the player, which is verified on the 39 songs where the
reference itself is clean.

## Unlike AKL, it needs no Arkos Tracker 2

AKM is an Arkos Tracker 3 format and `SongToAkm.exe` ships with the current
tracker. That removes AKL's permanent dependency on an AT2 install — which is
one of the two reasons to prefer it. The other is size.

But see the version trap below before assuming AT3's exporter is the one you
want.

## AKM DERIVES ITS PERIODS, AND ARKOS'S OWN TABLE DISAGREES WITH IT

This is the single most important thing to know about the format, and it is
not in the spec.

AKL ships a full 128-note period table. **AKM ships twelve entries — octave 0
— and the player derives every other octave at run time**, halving with
`srl h : rr l` and rounding if the last bit shifted out was set:

```
        ld a,b
        or a
        jr z,PLY_AKM_FindOctave_OctaveShiftLoop_Finished
PLY_AKM_FindOctave_OctaveShiftLoop:
        srl h
        rr l
        djnz PLY_AKM_FindOctave_OctaveShiftLoop
        jr nc,PLY_AKM_FindOctave_Finished
        inc hl
```

That is not the same function as Arkos's true note table. On the notes where
the halving lands exactly on `.5`, the two round opposite ways:

| note | AKM's halving | Arkos's table |
|--:|--:|--:|
| 18 | 1352 | 1351 |
| 21 | 1137 | 1136 |
| 23 | 1013 | 1012 |
| 28 | 759 | 758 |
| 49 | 226 | 225 |
| 56 | 151 | 150 |

Six notes, and AKM is **+1 on every one**. Measured 2026-09-05 against
`lib/akl_periods.asm`, which is Arkos's own table extracted from
`PlayerLightweight.asm`.

Two consequences:

- **`lib/akl_periods.asm` cannot be reused for AKM.** It is the true table,
  and a player using it would disagree with the player it is a port of. The
  BBC player generates its own table, `lib/akm_periods.asm`, from AKM's
  halving — so the table is provably the algorithm it replaces (decision:
  KC, 2026-09-05, "just build the table").
- **A +1 period difference against `SongToYm.exe` on those six notes is
  correct, not a defect** — the AKM analogue of AKL's documented eleven. Any
  other period difference is a regression.

## The version trap: AT3 ships a V0 player and a V1 exporter

`SongToAkm.exe` writes the format version into the first line of its source
export. Measured 2026-09-05:

| | writes |
|---|---|
| Arkos Tracker 3's `SongToAkm.exe` | `format V1` |
| Arkos Tracker 2's `SongToAkm.exe` | `format V0` |
| **AT3's own `players/playerAkm/sources/z80/PlayerAkm.asm`** | **`(format V0)`** |

So the player Arkos Tracker 3 ships cannot be the intended reader of what
Arkos Tracker 3's exporter produces, and `reference/AKM.md` — vendored from
that player's own `doc/` directory — documents V0.

It shows. EDGEA's instrument 9 is, in AT2's V0 export and in AKL, twelve
`0x52` cells then four arpeggio cells then the end marker. AT3's V1 export
adds a thirteenth `0x52` before the end marker, and **AT3's own replay does
not play it**: `SongToYm.exe` silences the channel at frame 96 where a
literal reading of the V1 data plays one more instrument cell and silences at
frame 102. Fourteen of EDGEA's seventeen instruments differ in length between
the two exporters, and not always in the same direction.

With the V0 export, EDGEA verifies clean. With the V1 export it does not.

**This does not mean V0 is the answer.** Over 64 CPC-clock corpus songs, 42
verify clean through the V1 exporter and 40 through V0, and AT2 refuses to
export several songs at all (it cannot load an AT3-saved `.aks`). The version
split is real, it explains EDGEA, and it is not what is causing most of the
remaining differences. Say which exporter a figure came from, the way this
repo already says which oracle a number came from.

## What is verified so far

Two oracles, and neither is this project.

### 1. Arkos's own annotation of the data

`SongToAkm.exe` without `-bin` writes the same song as assembler source with a
comment on **every byte** saying what it means:

```
db 126    ; New instrument (2). New escaped note: 76. Primary wait (0).
db 76     ;   Escape note value.
db 2      ;   Escape instrument value.
```

`tools/verify/akm_source_check.py` assembles that source, **proves it is byte
for byte the same as the binary export** (and refuses to report anything if it
is not), then replays the binary in `akm_reference.py` with its decode log on
and holds every decision against the comment at that address.

This is a much sharper instrument than a register log for the decode layers. A
register log only shows a fault once it has changed an audible register, by
which time the cause is hundreds of frames back; this shows it on the cell.

| | |
|---|--:|
| songs | 74 |
| cells, effects, instrument volumes and linker entries checked | **46,236** |
| disagreements | **0** |

That covers the note (reference, new escape, same escape), the instrument
(primary, secondary, new escape, same escape), the wait, all eight effects and
their data, every instrument cell's volume, and - the layer a cell check
cannot see, because a wrong track pointer still reads perfectly valid cells -
**the linker's per-channel track pointers, pattern heights and speed
changes**.

**So the format is understood.** That is what step 1 exists to establish.

### 2. `SongToYm.exe`, Arkos's own replay

Over every CPC-clock song in the corpus (11 Atari ST and MSX songs excluded:
they run their PSG at 2 MHz and 1.789 MHz and this player targets the CPC's
1 MHz path deliberately, so the period table is knowingly wrong for them):

| | |
|---|--:|
| CPC-clock songs | 64 |
| with no register difference outside the explained classes below | **39** |
| with differences still unexplained | 25 |

Two of the clean ones are worth naming for their length: **Targhan's *Dead On
Time*, 3,726 frames, and *Orion Prime L4*, 24,192 frames - the only difference
from Arkos's own player on either is the +1 above. Nothing else differs at
all.**

### The explained classes

| class | why it is not a defect |
|---|---|
| period +1 on six notes | AKM's octave halving against Arkos's true table, above. Inherent to the AKM player. |
| volume differing by exactly 1 | Arkos's own documented ±1 in the volume/pitch effects between its PC side and its Z80 player - the same tolerance `verification.md` records as a PASS for AKL's eleven. The annotation check proves both the instrument's volume nibble and the effect's inverted volume are read correctly, so the subtraction's inputs are right and only Arkos's arithmetic differs. |
| `env shape` | AKM inherits AKL's envelope limitation - shapes 8 and 0xa only. A tune whose real envelope is neither, and not one shifted pair either, cannot be represented; `tools/arkos.py` warns. |
| everything on a silent channel | Arkos leaves a silent channel's registers alone, so its period and mixer bits go stale. `compare_audible` already ignores this for AKL. |

### What is NOT explained, and is why step 1 is not signed off

**25 of the 64 songs still differ in ways none of those classes covers.** They
are overwhelmingly native `.aks` songs rather than `.sks` ones:

| folder | clean or +1-only | differs |
|---|--:|--:|
| `songs/STarKos` (`.sks`) | 39 | 7 |
| `songs/ArkosTracker2` (`.aks`) | 2 | 8 |
| `songs/ArkosTracker3` (`.aks`) | 1 | 4 |

StarKos is the older and poorer format and cannot express what a native Arkos
song can, so `.sks` tunes largely pass by never reaching whatever is wrong.

**The cause is not the decode.** The annotation check above proves the note,
instrument, wait, effects, instrument volumes and linker are all read exactly
as Arkos says they should be, on every one of these songs. The difference is
in *rendering*: which instrument cell is heard on which frame.

The clearest case, `FenyxKell - KellyOn.sks` channel 3, frame 100, traced in
full: both players agree for 100 frames; the cell at &44FE decodes identically
in both (note reference 1, new escape instrument 4, primary wait 0, volume
effect with inverted volume 5); every preceding cell has wait 0; the linker
agrees; no pattern boundary is near. Arkos nonetheless holds the channel
silent for one more line and starts instrument 4 four frames later than a
literal reading of the data does. **Not yet explained.**

## The 6502 player

`lib/akmplayer.asm`, written to `aklplayer.asm`'s conventions - X is the
channel for the whole of a channel's processing, Y the offset into the track
or instrument being read, per-channel state in three-byte arrays indexed by X.
25 bytes of zero page, the same as AKY.

**A rewrite, not a transcription.** `PlayerAkm.asm` uses `ld sp,` as a data
pointer, pushing the PSG registers out through a table of RET addresses, and
self-modifies an instruction operand for every value it reads from the song
header. Neither travels to a 6502. What is reproduced is its arithmetic,
statement for statement.

### Verified

`python tools/verify/akm_verify_corpus.py` builds, simulates and diffs the
player against `akm_reference.py` frame for frame across every song in
`tools/verify/akm_known_good.txt`:

| | |
|---|--:|
| songs | 39 |
| **identical to the reference on every frame** | **39** |
| differing | 0 |

Longest single runs: *Dead On Time* over all 3,726 of its calls and *Orion
Prime L4* over all 24,192, both identical.

### Cost

Cycles for one call at 2 MHz, including the whole AY-to-SN conversion:

| | mean | worst frame |
|---|--:|--:|
| across the 39 songs | **2,410** | 4,859 |
| the cheapest song | 2,239 | 3,989 |
| the dearest song | 2,680 | - |

For comparison on the same terms, AKL is 2,689 mean and 3,870 worst on Edge
Grinder's tune. **Targhan's own header warns that AKM is "much slower than the
generic one or the AKY player"** - up to 45 CPC scanlines - and on a Z80 that
is presumably so. On a 6502 it comes out slightly *cheaper* than AKL on
average, with a worse tail. The reason is that most of what AKM added over
Lightweight is decoding cleverness in the TRACK, which runs once a line, while
the per-frame path - instruments, effects, the period lookup - is nearly the
same work. Measure, do not assume, was the instruction; this is the measurement.

### Size, and the honest trade

| | AKL | AKM |
|---|--:|--:|
| player + `ay2sn` converter | 3,612 | **4,161** |
| EDGEA's tune data | 4,741 | **3,654** |
| **total** | 8,353 | **7,815** |

AKM's code is 549 bytes BIGGER, most of it the period table: AKL ships 128
notes and AKM needs 256, because its note index is 8-bit and wraps. The data
is 1,087 bytes smaller, so AKM wins overall by 538 bytes on this tune - and by
more the longer the tune, since only the data grows.

**So AKM is not simply "AKL but smaller".** It is smaller data and bigger code,
and on a short tune AKL can still win. `tools/compare_formats.py` measures both
on any song.

## Which songs reach which paths

`tools/survey_akm.py` exports every song in the corpus with
`SongToAkm --exportPlayerConfig`, which is Arkos's own statement of what a
tune uses, and reports what each one reaches. It writes
`build/akm-coverage.md`.

The result that matters: **`Targhan - Crtc.aks` reaches 21 of the player's 26
paths**, including the pitch table and two of the force-speed effects — three
of the five paths AKL has still never executed. It is the demo tune for that
reason and no other.

Four tunes between them reach everything the 75-song corpus reaches:

| tune | adds |
|---|---|
| `Targhan - Crtc.aks` | 21 paths, including the arpeggio and pitch tables, reset, both pitch directions, hardware sounds, SoftToHard, transpositions, speed tracks |
| `Totta - Hardy (MSX).aks` | SoftAndHard, and its arpeggio and pitch — the corpus's only SoftAndHard song |
| `Targhan - Midline Process - Carpet.sks` | SoftToHard with software pitch |
| `Playing with effects.aks` | Force Pitch Table Speed |

## What is NOT ported

`PlayerAkm_SoundEffects.asm` is vendored for completeness and is not ported.
`PLY_AKM_RT_WaitLong`, `PLY_AKM_RT_WaitShort` and `PLY_AKM_RT_CellRead` in
the Z80 player are **dead code** — nothing anywhere jumps to them, in either
Arkos source file — and are Lightweight leftovers. They are not ported and
their absence is not a gap.

## Traps

- **The song is exported at the address it will be played from.** AKM holds
  absolute pointers. Nothing checks this at run time.
- **Run `--check` before the simulator, always.** AT2's AKL exporter is known
  to emit data whose pointers leave the song, and fed that a 6502 replay does
  not fail, it *spins*. AT2's AKM exporter does the same on
  `Targhan - Crtc.aks`: `akm_reference.py` raises in milliseconds where a
  py65 harness would sit there. `tools/export_akm.py --check` replays the
  export in the Python reference first.
- **Target the CPC path.** `PLY_AKM_HARDWARE_CPC`, a 1 MHz PSG. The MSX,
  Spectrum and Pentagon period tables are for different clocks and are wrong
  for us — and a song *authored* on one of those machines carries its own
  clock, which `SongToYm`'s header states. Eleven corpus songs are in that
  class and are excluded from the figures above rather than counted as
  failures.
- **AKM shares AKL's envelope limitation** — shapes 8 and 0xa only — so it
  needs the same `ENV_BASE` treatment, and `tools/arkos.py`'s
  `envelope_base()` serves it unchanged. A tune whose real envelope is
  neither, and which is not one shifted pair either, cannot be represented at
  all: `arkos.py` warns, and `env shape` mismatches on those tunes are
  expected.
- **A path nothing has ever called is not a tested path.** Five of AKL's
  seven effects have still never executed. `tools/survey_akm.py` exists so
  that this port can say plainly which AKM paths its testing reached.
