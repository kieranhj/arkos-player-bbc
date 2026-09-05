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
expression numbering) and does **not** happen with any Targhan song tested,
nor with EDGEA — those use no arpeggio tables at all, which is exactly why it
was never seen before.

`--check` catches it:

```
python tools/export_akl.py songs/mysong.aks --addr 0x3000 --check
```

It replays the export in the Python reference and reports the table sizes,
the highest index the tracks actually reference, the features the song uses,
and any read outside the song. Run it on any new tune before trusting it.

If a song trips this, use AKY (via Arkos Tracker 3) instead.

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

That last one is why `ENV_BASE` exists in `lib/aklplayer.asm`. **It is 12 for
EDGEA and a different tune may need a different value**, or AKG, which carries
the shape properly for 204 more bytes. `ENV_BASE` also appears in
`tools/verify/akl_reference.py`; if one changes the other must, or the
harness will "prove" the player correct against a reference carrying the same
mistake.

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
