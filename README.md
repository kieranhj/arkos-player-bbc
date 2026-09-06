# arkos-player-bbc

**Arkos Tracker music on the BBC Micro.** Three 6502 replays — AKL, AKM, AKY —
and the AY-3-8912 → SN76489 layer they need on a machine that has no AY at all.

A tracker replay is a different trade from a register log. Edge Grinder's
349-second tune is 23,514 bytes as a compressed SN76489 log and **4,741 bytes
as Arkos tracker data**, and the replay is cheaper per frame than the log
player as well.

Nobody had done this on the BBC. Arkos ships 6502 players only for AKY, and
only for hosts with a real AY (Apple II with a Mockingboard, Oric, Atari with a
SONari). And **`lib/akmplayer.asm` is the only 6502 AKM player there is**, on
any machine: AKM is Arkos's smallest format and its documented successor to
Lightweight, and until now it was Z80 only.

MIT, except the tunes in `songs/` — see [Credit](#credit).

**Every line of new code here was written by Claude** (Anthropic's Claude
Code), directed and reviewed by me. The 6502 replays, the conversion layer, the
Python tooling and the documentation are all its work; the design decisions in
[`docs/decisions.md`](docs/decisions.md) are mine. That is also why so much of
this repository is measurement rather than assertion — every figure in every
document says what it was measured on and when, and nothing is believed without
an acceptance test. Treat it as you would any other code you did not write
yourself: the verification chain in [`docs/verification.md`](docs/verification.md)
is there to be re-run.

## Listen to it

Both demo discs run in the browser, on a stock Model B — no second processor,
no sideways RAM, nothing but a BBC Micro and its sound chip:

- **[AKM — Targhan, *Crtc*](https://bbc.xania.org/?disc=https://bitshifters.github.io/content/wip/arkos-akm-wip.ssd&autoboot&model=B)**
- **[AKY — Rhino, *Acid Demo*](https://bbc.xania.org/?disc=https://bitshifters.github.io/content/wip/arkos-aky-wip.ssd&autoboot&model=B)**

**SPACE** mutes, **B** cycles the bass through periodic noise, the software
voice and none at all, **ESCAPE** quits. The red band is the music: what you
are looking at is the cost of the frame you are listening to.

*Crtc* leans hard on notes below the SN76489's 122 Hz floor, so **B** is worth
pressing — that is the whole argument of [`docs/ay-to-sn.md`](docs/ay-to-sn.md)
in a form you can hear.

## What is here

```
lib/ay2sn.asm       the spine: ay_regs -> SN76489            (BBC-specific)
lib/aklplayer.asm   AKL replay, hardware-free                (ours)
lib/akmplayer.asm   AKM replay, hardware-free                (ours; the only one)
lib/akyplayer.asm   AKY replay, hardware-free                (ported, MIT)
example/            the demo, and five discs built from it
tools/              exporters, the verification harness, a WAV renderer
reference/          Arkos's own sources, vendored unmodified
```

Every player writes the fourteen AY registers into one buffer. `ay2sn` converts
that buffer to the SN76489, once a frame. Nothing else in the library knows
what machine it is on, so a replay alone travels to an Oric or an Apple II.

```
  aklplayer.asm ─┐
  akmplayer.asm ─┼──►  ay_regs (14 bytes)  ──►  ay2sn.asm  ──►  &FE4F
  akyplayer.asm ─┘                                            (System VIA)
```

## Which one to use

| | player + workspace | tune data | mean cycles a call | worst frame | needs |
|---|--:|---|--:|--:|---|
| **AKL** | 3,685 | small | 2,454–2,541 | 3,594–3,900 | an Arkos Tracker **2** install; its exporter can emit unplayable data |
| **AKM** | 4,234 | **smallest, every tune** | 2,482–2,805 | 4,229–5,032 | nothing special; AT3 exports it |
| **AKY** | 2,750 | 1.7–3.8× the others | **2,050–2,223** | **2,714–2,983** | nothing special |

Measured in py65 at 2 MHz over five tunes, including the whole AY→SN
conversion and the bass voice. Full per-tune tables, and the same comparison
against VGC, VGI, AKG and raw VGM, are in
[`docs/performance.md`](docs/performance.md#7-choosing-a-format-the-full-tables).

The short version:

- **AKM for a long tune, AKL for a short one.** AKM's data is smaller on every
  song measured, but its player is 549 bytes bigger, so on *total* RAM it only
  wins once the tune is long enough to pay for that — 538 bytes better on Edge
  Grinder's 349 seconds, 302 bytes **worse** on Dead On Time's 149.
- **AKY if cycles matter**, and especially the worst frame: it does almost
  nothing per call, so `ay2sn` becomes the whole cost. It pays for that in
  tune data.
- **Anything new should start with AKM.** AKL is withdrawn upstream — Arkos
  Tracker 3 ships no Lightweight player, documentation or exporter — so it
  needs an AT2 install permanently, and AT2's exporter has a bug that produces
  songs no player can play (`export_akl.py --check` refuses them). See
  [`docs/format-akl.md`](docs/format-akl.md).
- A tracker replay beats a register log on RAM by 1.4× to **2.0×**, and the
  longer the tune the wider the gap. A log stores the output, which grows with
  length; a song mostly does not. Orion Prime is 484 seconds in 2,320 bytes.
- **AKG has no 6502 player anywhere.** [`docs/porting.md`](docs/porting.md) is
  the route if you want one.

## Using it

Four things, and they are all `example/demo.asm` does:

```
ENV_BASE = 8                        \ 0. AKL only: the song's envelope pair
BASS_MODE = 2                       \    and which bass voice to assemble:
                                    \    -1 keeps all three and chooses at
                                    \    run time, 0/1/2 fixes one
ORG &70
INCLUDE "lib/aklplayer.h.asm"       \ 1. the player's zero page (22 bytes;
                                    \    akyplayer/akmplayer are 25)
...
INCLUDE "lib/ay2sn.asm"             \ 2. the spine, then the player
INCLUDE "lib/aklplayer.asm"
...
    lda #LO(song) : ldx #HI(song)   \ 3. once, with the exported data's
    ldy #0                          \    base (subsong index in Y; AKY
    jsr akl_init                    \    has no Y and parses its header)
...
.every_field                        \ 4. at the song's OWN replay rate,
    jsr akl_play                    \    from your VSync IRQ
    jmp ay2sn
```

Five things a host gets wrong silently:

- **`ENV_BASE` belongs to the song, not the player**, and `lib/aklplayer.asm`
  deliberately does not default it. 8 is right for almost every tune; a tune
  whose real envelope AKL could not encode needs the pair shifted (EDGEA needs
  12). `tools/arkos.py`'s `envelope_base()` works it out and
  `example/build.py` passes it in.
- **Call it at the rate the song was written for.** A song is authored for a
  fixed number of replays a second and **the AKL and AKY exports do not carry
  that number**. Most Arkos songs are 50 Hz, so a call per field is right;
  Targhan's *Dead On Time* is 25 Hz, and calling it every field plays it at
  exactly double speed, in tune, with nothing in the register stream to
  indicate a fault. `tools/arkos.py` reads the rate out of a `SongToYm.exe`
  header, the only place it is written down.
- **Call it with interrupts off, or from an interrupt handler.** `ay2sn` sets
  the System VIA's DDRA once on entry and every SN76489 write after that
  relies on it still being set — so nothing that changes DDRA may run in the
  middle, and on a stock machine the MOS's own 100 Hz keyboard scan does. A
  VSync IRQ handler satisfies this for free. Anywhere else, wrap it in
  `sei`/`cli`. It is worth about 60 cycles a call.
- **AKL only: check the transposition at position 0.** AKL's linker encodes a
  transposition only when it *changes* and the player starts at zero, so a song
  whose first position is transposed depends on AT2's exporter writing it there
  — and for one song in the 62 it can export, it does not. That is notes in the
  wrong key, in tune with themselves, until the linker next sets one.
  `export_akl.py --check` refuses such an export and prints the three stores to
  put after `akl_init`; `example/build.py` applies them for you.
- **`akl_silence` mutes instead of a frame of music, never as well as.**
  Running the player and silencing the chip afterwards puts a burst of the
  tune's own volumes out fifty times a second, and crackles.

**The bass.** The SN76489's lowest note is 122 Hz and a third to nearly half
of every tune measured falls below it. Mode **0** shifts those notes up an
octave; **mode 2, the default on all five discs, synthesises them with periodic
noise** and needs nothing from the host; mode **1** bit-bangs a real square wave
from a User VIA timer and needs an interrupt wired up. There is one bass voice
either way and it is sticky.

**`BASS_MODE` picks it at assembly time and is not defaulted**, like
`ENV_BASE`. Naming one is worth **589 bytes** if you want no bass at all and
217 if you want the periodic voice — and a host that wants none pays 120 cycles
a call for the option unless it says so. `BASS_MODE = -1` assembles all three
and lets you store into `bass_mode` at run time, which is what the demo does so
its B key can compare them by ear. What each costs, and how to wire mode 1, is
in [`docs/ay-to-sn.md`](docs/ay-to-sn.md#choosing-bass_mode-and-wiring-mode-1);
the sizes are in [`docs/performance.md`](docs/performance.md).

**Six-channel songs** carry two PSGs and the BBC has one sound chip. `aky_init`
reads the count out of the AKY header and plays the first, ignoring the rest —
which is often exactly right rather than a compromise, since Arkos songs
sometimes ride event data on a second PSG, and Rhino's Acid Demo does.
[`docs/porting.md`](docs/porting.md).

## Build and verify

Run everything from the repo root. Needs [beebasm](https://github.com/stardot/beebasm),
`pip install py65 numpy`, and an Arkos Tracker install to export songs and to
be the oracle.

```
python example/build.py                       # ARKOS-AKL / -AKY / -AKM .SSD
python example/build.py --extra               # ARKOS-EDGEA.SSD, ARKOS-ORION.SSD
python example/build.py --song X.aks --disc D # any other song
python tools/verify/verify.py --player akl    # prove the player still works
python tools/verify/akm_verify_corpus.py      # prove AKM on all 39 of its songs
python tools/make_tables.py --check           # prove the tables still match
python tools/compare_formats.py               # regenerate the format tables
python tools/survey_tunes.py                  # what each song in a corpus stresses
```

Five discs. **EDGEA** is the tune the library was built for and the only one
here that uses the hardware envelope; **Orion Prime Level 4** has the hardest
bass of the 75 songs surveyed and is where a one-voice bass shows its limit.
The **AKM** disc's *Crtc* was picked by measurement: of those 75 songs it
reaches 21 of the player's 26 code paths, more than any other.

**Nothing is checked against itself.** A Python transcription of Arkos's own
Z80 player is checked against a `.ym` register log from `SongToYm.exe`; the
6502 is checked against that transcription in py65, frame for frame; and the
demo disc is checked against the simulation by capturing SN76489 writes out of
jsbeeb — the one class of fault everything upstream is blind to, since it all
runs in a simulator. Current results, the AKM annotation oracle, and the fact
that **the oracle is version-sensitive** (the same comparison gives 11
mismatches against AT2 and 431 against AT3, with the 6502 byte-identical to
its reference in both runs) are in
[`docs/verification.md`](docs/verification.md).

## Credit

Arkos Tracker is by **Julien Névo (Targhan/Arkos)** and everything here rests
on his work and his format documentation. The AKY player is derived from
**Krzysztof Dudek (xxl)**'s Atari 8-bit port; there is a second 6502 AKY port
for the Apple II and Oric by **Arnaud Cocquière (GROUiK/French Touch)**. All
MIT — see [`LICENSES/PROVENANCE.md`](LICENSES/PROVENANCE.md) for exactly which
file came from where. The tunes in `songs/` are **not** MIT: they are used by
permission of their composers (`songs/README.md`).

**The AY→SN76489 conversion is Simon Morris (simondotm)'s, and this is a
runtime implementation of it, not an independent one.** Close enough now that
on a tune with no hardware envelope it is not an approximation of his output
at all — it *is* his output, every tone period, tone volume and noise byte,
over all 9,600 calls of Rhino's Acid Demo.
[`ym2sn.py`](https://github.com/simondotm/ym2149f) is where the period
arithmetic, the volume mapping, the noise-rate matching, the periodic-noise
bass and the priority-channel idea all come from, expertly tuned over a long
time and against real ears. The software bass voice is his too, from
`vgcplayer_bass.asm`, and `sn_write` comes from
[vgm-player-bbc](https://github.com/simondotm/vgm-player-bbc) — as does the
**VGC** format the comparison tables measure against. **VGI**, the interleaved
variant in those tables, is so far only a branch of
[kieranhj's fork](https://github.com/kieranhj/vgm-player-bbc) of that project.

What is new here is the AKL replay, the AKM replay, the BBC port of the AKY
replay, and putting that conversion in the 6502 rather than in a build step.
What is not new is every idea underneath them. The AKL work was built for the
[Edge Grinder BBC port](https://github.com/kieranhj/edge-beeb) and extracted
from it.

## Documentation

**The formats**

- [`docs/format-akl.md`](docs/format-akl.md) — AKL, the three conventions that
  had to be understood, and how its exporter can lie
- [`docs/format-akm.md`](docs/format-akm.md) — AKM, why it needs its own period
  table, and the V0-player/V1-exporter split in Arkos Tracker 3

**The conversion, the cost, and how any of it is known to work**

- [`docs/ay-to-sn.md`](docs/ay-to-sn.md) — the conversion, the bass, and what a
  per-frame converter cannot do
- [`docs/performance.md`](docs/performance.md) — where the cycles go, what was
  taken back, and the full format comparison
- [`docs/verification.md`](docs/verification.md) — the oracle chain and how to
  re-run it
- [`docs/fidelity-plan.md`](docs/fidelity-plan.md) — the envelope and the two
  bass voices, what each cost, and what is still open

**Where it goes next**

- [`PLAN.md`](PLAN.md) — what is left to do, and nothing else
- [`docs/akm-open-questions.md`](docs/akm-open-questions.md) — the three AKM
  questions, parked with reproduction steps
- [`docs/porting.md`](docs/porting.md) — taking a replay to another 6502, to a
  real AY, or porting the one format still without a player
- [`docs/decisions.md`](docs/decisions.md) — KC's decisions, binding
- [`docs/history.md`](docs/history.md) — how it got built, and what the plan
  got wrong on the way
