# What is verified, and how to re-run it

```
python tools/verify/verify.py                            # AKL, default song
python tools/verify/verify.py --player aky --song X.aks
python tools/verify/verify.py --frames 3000              # a quick pass
python tools/verify/verify.py --snf build/runtime.snf    # and capture audio
python tools/make_tables.py --check                      # the tables
```

Run from the repo root: beebasm resolves INCLUDEs from the working directory.
Needs beebasm, `pip install py65 numpy`, and an Arkos install for the oracle.
Without an oracle it still runs the 6502-against-reference check and says
which check it skipped.

## The chain

Nothing is checked against itself.

1. **`akl_reference.py` against a `.ym`.** The reference is a Python
   transcription of Arkos's Z80 `PlayerLightweight.asm`. The `.ym` is the AY
   register log `SongToYm.exe` produces by running **Arkos's own full
   player** over the same song — an oracle outside this project entirely.
   This catches a misunderstanding of the format.
2. **The 6502 against the reference**, in py65, frame for frame, comparing
   `ay_regs`. This catches a 6502 bug. It found one in the original AKL work
   that would have been near-impossible to hear out: the hardware instrument
   path computed the software period and never stored it.
3. **The demo disc against the simulation.** Capture SN76489 writes out of
   jsbeeb and find them in the simulated stream. This catches a wiring,
   paging or interrupt bug. Twenty consecutive fields of the AKY demo matched
   the simulation exactly on 2026-09-05 — at four alignments 48 frames apart,
   because that passage of the tune repeats; every match was byte for byte.

For AKY there is no Python transcription and none is needed. AKY is close to
a register stream, so the 6502's `ay_regs` are compared straight to the
oracle, which folds steps 1 and 2 into one stronger check.

## Reading the result

The comparison deliberately ignores what cannot be heard — `compare_audible`
in `verify.py` is where that judgement lives, and
[`format-akl.md`](format-akl.md) explains the three conventions behind it.

Known-good results, 2026-09-05:

| player | tune | oracle | result |
|---|---|---|---|
| AKL | Dead On Time (Ingame), 3,726 frames | AT2 | identical to reference; **NONE** audible |
| AKL | EDGEA, 17,446 frames | AT2 | identical to reference; `{'ch2 period': 11}` **with `ENV_BASE = 12`**; the default 8 gives `env shape` mismatches, correctly - see `format-akl.md` |
| AKL | Orion Prime L4 Theme 1 | AT2 | identical to reference; **NONE** audible |
| AKY | Rhino - Acid Demo 21 (six channels), whole tune | AT3 | **NONE** audible |
| AKY | Rhino - Acid Demo 07 (three channels), whole tune | AT3 | **NONE** audible |
| AKY | EDGEA, whole tune | AT3 | volumes and periods differ; the periods track the AT2/AT3 replay change below, the volumes are not yet explained |

**Eleven channel-2 periods off by one is correct.** It is Arkos's own
documented plus-or-minus-one in the volume/pitch effects between the PC side
and the Z80 player. Anything else is a regression.

## The replay rate is not in the exported data

`verify.py` prints it, because nothing else will tell you and getting it
wrong is silent:

```
replay:  25 Hz - 3726 calls, 149.0 seconds of music
         NOT 50 Hz: a host running off VSync must call the
         player every 2 fields, not every field.
```

The player replays once per call and has no idea how often that should be.
Targhan's *Dead On Time* is a 25 Hz song and the first version of the demo
disc called it every field, which played it at exactly double speed - in
tune, with the right notes, and no way to tell from the register stream that
anything was wrong. **The frame-for-frame checks above cannot catch this**:
they compare call for call, so a player running twice too fast is perfectly
correct on every one of them. It was caught by ear, and then confirmed
against Arkos's own WAV render (149.0 s, against 3,726 calls at 50 Hz =
74.5 s).

`tools/arkos.py` reads the rate out of a `SongToYm.exe` header, which is the
only place it is written down.

## The oracle is version-sensitive

The same EDGEA comparison gives:

| oracle | audible mismatches |
|---|---|
| Arkos Tracker 2's `SongToYm.exe` | `{'ch2 period': 11}` |
| Arkos Tracker 3.7's `SongToYm.exe` | `{'ch2 period': 431, 'ch1 period': 360}` |

The 6502 was byte-identical to the reference in both runs, so what changed is
**Arkos's own replay**, somewhere between AT2 and AT3. It is not a small
change and the changelog does not mention it.

`verify.py` prefers AT3's `SongToYm.exe` and prints which one it used. To pin
the AT2 baseline, hide AT3:

```
ARKOS3_HOME=/nonexistent python tools/verify/verify.py --song EDGEA.SKS
```

**Always say which oracle a figure came from.**

## The tables

`tools/make_tables.py --check` proves `lib/akl_periods.asm` and
`lib/ay2sn_tables.asm` still match their derivations. Both were committed to
the original project with no generator at all, so nobody could say where a
number came from; all five tables are now reproduced from first principles or
extracted from Arkos's own source. The comparison is on the data, not the
file text, so comments and row widths are free to change.
