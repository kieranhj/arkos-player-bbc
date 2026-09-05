# AKL, and how to get a song into it

AKL — Arkos's "lightweight" format — is patterns, instruments and an order
list, replayed by `lib/aklplayer.asm`. The whole of Edge Grinder's 349-second
tune is 4,741 bytes of it.

`reference/SongLightweightExportFormat.md` is the authoritative spec, vendored
here. `reference/PlayerLightweight.asm` is Arkos's Z80 player, which
`lib/aklplayer.asm` reproduces. Read those before this.

## It is withdrawn upstream

Arkos Tracker 3 has removed the Lightweight player, its documentation and
`SongToLightweight.exe`. AKM's own doc says why: *"This player may actually
replace Lightweight!"* — AKM is smaller (3,654 bytes for the same tune) and
more capable.

Consequences you cannot design around:

- **`tools/export_akl.py` requires an Arkos Tracker 2 install and always
  will.** Set `ARKOS2_HOME` or pass `--exporter`.
- Nobody upstream will fix an AKL exporter bug, and there is one (below).
- `reference/` keeps AT2's Lightweight sources because AT2 is no longer
  distributed and nowhere else has them.

## The exporter can emit unplayable data

AT2's `SongToLightweight.exe` will, without any warning, export a song whose
tracks reference an arpeggio table it did not write.

Measured on Rhino's Acid Demo, 2026-09-05:

```
arpeggio tables: 10 (highest referenced: 29)
*** THIS EXPORT IS NOT PLAYABLE ***
    the tracks reference arpeggio 29, but only 10 were exported
```

The arpeggio index table runs from the header's arpeggio pointer to its pitch
pointer — ten entries, 0 to 9. Track data asks for number 29. The player
multiplies by two, adds the table base and reads two bytes of *arpeggio
content* as a pointer, which sends it off into unrelated memory.

**This is not a defect in `lib/aklplayer.asm`.** Arkos's own Z80 player does
`ld a,b : and %11111` then `add a,a` and indexes the same table with the same
number; read literally it reads the same out-of-range entry. The data is
internally inconsistent and no player can play it.

It is reproducible across three iterations of that song (which share their
expression numbering), and **it is not confined to Rhino's tunes**: AT2 does
the same to Targhan's own *Crtc*, referencing arpeggio 29 there too. It does
not happen with a song that uses no arpeggio tables at all — EDGEA, *Dead On
Time* — which is exactly why it went unseen for so long.

`--check` catches it:

```
python tools/export_akl.py songs/mysong.aks --addr 0x3000 --check
```

It replays the export in the Python reference and reports the table sizes,
the highest index the tracks actually reference, the features the song uses,
and any read outside the song. Run it on any new tune before trusting it.

If a song trips this, use AKY (via Arkos Tracker 3) instead.

**The reference itself used to spin on it too.** When the bad arpeggio's end
markers point at each other rather than off the end of the song, there is no
out-of-range read to catch: `manage_effects` just hops between them forever.
Both of its loops are bounded now and raise `AklDataError` instead, because a
checker that hangs is worse than no checker - it looks like slow progress.
Measured on *Crtc*, 2026-09-05: it hung at frame 1422 and now refuses in
milliseconds.

**And run `--check` FIRST, because the 6502 player does not fail on this
data - it SPINS.** Measured 2026-09-05: `akl_reference.py` raises at frame
414 of Rhino's tune in a few milliseconds, but `lib/aklplayer.asm` fed the
same export follows the wild pointer into memory that is not code and never
returns, so a py65 harness sits in `while pc != RET: step()` for as long as
you let it. An hour of silence, not an error. `tools/compare_formats.py`
therefore asks the Python reference whether an export plays before it lets
the simulator anywhere near it, and so should anything else that measures a
tune it has not seen. On real hardware this is a hung machine.

## Three conventions that had to be understood

These came out of proving the Python reference against `SongToYm.exe`, and
each one reads as a bug until you know it is not:

- **`SongToYm` zeroes registers that cannot be heard.** R6 when no channel
  has the noise open; R11/R12 when nothing uses the envelope. On the frames
  where they do matter, everything agrees exactly. A raw fourteen-register
  diff reads as 11% wrong and is nothing of the kind.
- **Arkos's player does not clear a silent channel's tone-disable bit.**
  1,239 mixer differences on EDGEA, every one on a channel at volume zero.
- **AKL cannot encode every envelope shape.** The format supports 8 and 0xa
  only. EDGEA uses 12 throughout, and the exporter silently substitutes 8 — a
  saw-down where the tune wants saw-up.

That last one is why `ENV_BASE` exists in `lib/aklplayer.asm`. AKL stores one
BIT of shape and it means `ENV_BASE` or `ENV_BASE + 2`; **the format defines
those as 8 and 10, so 8 is the default and most tunes need nothing**. Set it
only for a tune whose real envelope AKL could not encode and the exporter
substituted one it could — EDGEA is envelope 12 throughout and needs
`ENV_BASE = 12`.

**It is not defaulted in the library at all**, because it is a property of
the SONG and a default is exactly how it came to be 12 — right for the one
tune it was written for and wrong for every other. The host defines it before
including the player, and `tools/arkos.py`'s `envelope_base()` works it out:
`SongToAkg.exe`'s SOURCE export names the true shape in a comment, so it runs
that and reads it. `example/build.py` passes the answer through to the disc
and `tools/verify/verify.py` uses the same value for the player and the
Python reference, so the two cannot drift.

Getting it wrong is visible either way: `verify.py` reports `env shape`
mismatches. Targhan's Orion Prime uses 8 and 10 and produced 362 of them
while the constant was 12; EDGEA produces 209 while it is 8. With
`envelope_base()` choosing, both are clean.

## Traps

- **The song is exported at the address it will be played from.** AKL holds
  absolute pointers. Nothing checks this at run time: a wrong address plays
  happily for thousands of frames before the stream runs off the end of what
  it was given.
- **Paths nothing has ever called are not tested paths.** Pitch tables,
  soft-and-hard instruments and effects 1, 2, 5 and 6 have still not been
  exercised by any verified tune. They are written and they look right; that
  is not the same thing. `--check` reports what a song uses.
- One real bug was found in this class during the extraction, in the Python
  reference: the arpeggio loop offset is sign-extended by the Z80's `sra` and
  then used as an **unsigned** 0-255 index (`ld l,a : ld h,0`). Without the
  mask the reference indexes backwards out of the song. The 6502 gets this
  right by construction, using Y.
