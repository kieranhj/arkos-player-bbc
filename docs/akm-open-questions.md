# AKM: what is still open

Three things, deliberately parked. None blocks `lib/akmplayer.asm`, which is
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

# 2. The tunes with a different PSG clock

Eleven corpus songs are excluded from every figure in these documents, and
they are excluded for a good reason rather than because they fail: **their
PSG is not the CPC's.**

| machine | PSG clock | `PLY_AKM_HARDWARE_*` |
|---|--:|---|
| Amstrad CPC | 1,000,000 Hz | `CPC` - what we target |
| Spectrum | 1,773,400 Hz | `SPECTRUM` |
| MSX | 1,789,773 Hz | `MSX` |
| Pentagon | 1,750,000 Hz | `PENTAGON` |
| Atari ST | 2,000,000 Hz | (none - Arkos has no ST player) |

`SongToYm.exe` writes the song's real clock into its YM header, which is how
`tools/verify/akm_corpus.py` separates them; `akm_known_good.txt` lists all
eleven with their clocks. Nine are at the ST's 2 MHz - eight Doclands tunes
and *Excellence in Art 2018 - Just add cream* - and two at the Spectrum's
1,773,400 Hz: *Totta - BaraBadaBastu* and *Totta - Room5 (MSX)*.

**Do not go by the name.** Four other songs with `(MSX)` in the title -
including *Totta - Hardy* - carry a 1 MHz clock and are in the CPC corpus.
The YM header is the only thing that says which chip a tune was written for.

## Why this is interesting rather than a chore

Nothing about the *player* is CPC-specific. The hardware choice is one table:
twelve octave-0 periods, which `PLY_AKM_PeriodTable` gives for all four
machines and which the octave halving expands. So an ST or Spectrum build is
`lib/akm_periods_st.asm` beside `lib/akm_periods.asm` and a constant - no
change to `akmplayer.asm` at all.

What makes it more than a table swap is the bass. **The SN76489's floor does
not move** - its lowest note is 122 Hz whatever the source chip ran at - but
an ST song's periods mean different *frequencies*, so the share of the tune
below that floor changes, and the ST tunes are written for a 2 MHz PSG with a
very different bass register. That is the bass work in
[`fidelity-plan.md`](fidelity-plan.md) exercised against material it has never
seen.

Note that `SongToAkm` will happily export any of them and nothing warns that
the resulting periods suit a different chip. The check is the YM header's
clock, and `akm_corpus.py` is where that check lives.

**Order of work**: after the two questions above. It is a genuine extension,
not a loose end - and it is the cheapest way this library has of reaching a
much bigger body of music.

---

# 3. SoftAndHard has still never executed

Of the 75 songs in the corpus, **exactly one uses SoftAndHard instruments**:
`Totta - Hardy (MSX)`, which despite its name runs at 1 MHz and is in the CPC
corpus. It is also one of the 25 songs with the rendering discrepancy above.

So the only route to exercising that path runs through question 1. Until then
`lib/akmplayer.asm`'s SoftAndHard branch is written, looks right, and has
never run - which, as this repo keeps saying, is not the same thing.

`tools/survey_akm.py` is what establishes this; it reports the paths no song
in the corpus reaches at all.
