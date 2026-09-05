# AKM: what is still open

Two things, deliberately parked. Neither blocks `lib/akmplayer.asm`, which is
verified frame for frame against `tools/verify/akm_reference.py` on the corpus
in `tools/verify/akm_known_good.txt`.

---

# 1. The rendering discrepancy — 25 songs

## What it is

On 25 of the 64 CPC-clock corpus songs, `akm_reference.py` and Arkos's own
replay (`SongToYm.exe`) produce different registers in ways that none of the
explained classes in [`format-akm.md`](format-akm.md) covers.

**It is not a decode fault, and that is established rather than assumed.**
`tools/verify/akm_source_check.py` holds the reference's decode against
Arkos's own byte-by-byte annotation of the same data — the note, the
instrument, the wait, all eight effects and their data, every instrument
cell's volume, and the linker's per-channel track pointers, pattern heights
and speed changes. **74 songs, 48,201 checks, zero disagreements**, including
every one of these 25.

So both players read the same bytes and agree on what every one of them
means. They disagree about **which instrument cell is heard on which frame**.

## The case traced to the bottom

`FenyxKell - KellyOn.sks`, channel 3, frame 100. Reproduce with:

```
python tools/verify/akm_source_check.py "<AT3>/songs/STarKos/FenyxKell - KellyOn.sks"
```

The two players agree exactly for 100 frames — a non-trivial figure
(11,0,0,0, 12,0,0,0, 13,0,0,0, 11,10,9,0) driven by an instrument that
restarts on every new cell, so this is real agreement and not coincidence.
Then:

| | frames 100-103 | 104-111 | 112-119 |
|---|---|---|---|
| ours | instrument 4 (10,10,10,9) | instrument 12 (9,9,9,8), then 4 again | ... repeating every 8 frames |
| Arkos | silent | instrument 4, all 8 cells (10,10,10,9,9,9,8,8) | instrument 12, all 8 cells (9,9,9,8,8,8,7,7) |

Everything about the cell at `&44FE` checks out against Arkos's own comment:

```
&44FE 0C  Note with effects flag.
&44FF 71  New instrument (4). Note reference (1). Primary wait (0).
&4500 04    Escape instrument value.
&4501 52    Volume effect, with inverted volume: 5.
```

Wait 0, so one line. Every preceding cell on that channel is also wait 0. The
linker agrees. No pattern boundary is near — our only linker read in the first
120 frames is at frame 0.

Arkos nevertheless holds the channel silent for one more line and then plays
each instrument to its full eight cells, i.e. **its line lasts 8 frames where
ours lasts 4**, from frame 100 onward.

## What was ruled out

- **The decode**, by the annotation oracle above.
- **A systematic line-rate error.** Our total tune length matches Arkos's
  closely: KellyOn 3,509 frames to the loop against Arkos's 3,592, Crtc 11,525
  against 11,589, EDGEA 17,447 against 17,446. We are not steadily ahead.
- **The obvious linker misread.** The state byte `&43A6 = 0xAB` decodes as
  speed change, height change and a new track for each of the three channels,
  exactly as Arkos annotates it; the speed is 4 and the height byte is
  `0x2C` = 44, both confirmed against the annotation.
- **The V0/V1 exporter split** ([`format-akm.md`](format-akm.md)). It explains
  EDGEA and not this: 42 songs verify clean through the V1 exporter and 40
  through V0, and KellyOn fails through both.
- **The unconditional track-pitch add**, and the `>=` in the instrument speed
  comparison. Both were tested by substitution and changed nothing.

## The strongest lead

Linker **position 1** carries **speed 8**, and 25 lines of position 0 at speed
4 is exactly 100 frames. If Arkos leaves position 0 after 25 lines rather than
the 44 the height byte states, everything observed follows. Nothing in
`PlayerAkm.asm` or `AKM.md` explains why it would.

Against that: our whole-tune length is *shorter* than Arkos's, not longer, so
if we are overstaying in patterns the error cannot be general.

## Where to pick it up

1. `SongToAkg.exe`'s **source** export annotates the pattern structure
   differently from AKM's. If it states a line count per position, that
   settles whether 44 is the number of lines.
2. `SongToRaw.exe` / `SongToRawLinear.exe` dump the song without a player at
   all, which would give the intended cell-per-frame timeline directly.
3. Ask Targhan. This is worth reporting alongside the V0-player/V1-exporter
   split, which he will want to know about anyway.

---

# 2. The Atari ST and MSX tunes — worth exploring

Eleven corpus songs are excluded from every figure in these documents, and
they are excluded for a good reason rather than because they fail: **their PSG
is not the CPC's.**

| machine | PSG clock | `PLY_AKM_HARDWARE_*` |
|---|--:|---|
| Amstrad CPC | 1,000,000 Hz | `CPC` — what we target |
| MSX | 1,789,773 Hz | `MSX` |
| Spectrum | 1,773,400 Hz | `SPECTRUM` |
| Pentagon | 1,750,000 Hz | `PENTAGON` |
| Atari ST | 2,000,000 Hz | (none — Arkos has no ST player) |

`SongToYm.exe` writes the song's real clock into its YM header, which is how
`tools/verify/akm_corpus.py` separates them. `akm_known_good.txt` lists them
with their clocks.

The tunes are `Doclands - Buzz-o-Meter (ST)`, `GinFizz`, `Pong Cracktro (ST)`,
`Slowly But (ST)`, `The Rivals (ST)`, `The Saga (ST)`, `Tiny Things (ST)`,
`Truly Yours (ST)`, `Your Credits (ST)`, and Totta's `Crawlers (MSX)`,
`Hardy (MSX)`, `Mellow (MSX)`, `Rezzy (MSX)`, `Room5 (MSX)` — a lot of good
music, and some of it stresses the player harder than anything in the CPC set:
**`Totta - Hardy (MSX)` is the only song in the whole corpus that uses
SoftAndHard**, which is otherwise a path nothing has ever executed.

## Why this is interesting rather than a chore

Nothing about the *player* is CPC-specific. The hardware choice is one table:
twelve octave-0 periods, which `PLY_AKM_PeriodTable` gives for all four
machines and which the octave halving expands. So an ST or MSX build is
`lib/akm_periods_st.asm` beside `lib/akm_periods.asm` and a constant — no
change to `akmplayer.asm` at all.

Two things make it more than a table swap, and both are the interesting part:

- **The SN76489's floor moves.** Its lowest note is 122 Hz regardless, but an
  ST song's periods mean different *frequencies*, so the share of the tune
  below the floor changes and the bass voice work in
  [`fidelity-plan.md`](fidelity-plan.md) is exercised differently. The ST tunes
  are mostly written for a 2 MHz PSG with a very different bass register.
- **It would exercise SoftAndHard for the first time**, and the hardware
  envelope paths much harder than the CPC corpus does.

Note that `SongToAkm` will happily export any of them; nothing warns that the
resulting periods suit a different chip. The check is the YM header's clock,
and `akm_corpus.py` is where that check lives.

**Order of work**: after the 6502 player is proved and on a disc. It is a
genuine extension, not a loose end — and it is the cheapest way this library
has of reaching a much bigger body of music.
