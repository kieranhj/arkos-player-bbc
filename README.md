# arkos-player-bbc

**Arkos Tracker music on the BBC Micro.** Two 6502 replays and the
AY-3-8912 → SN76489 layer they need to play on a machine the format was
never meant for.

A tracker replay is a different trade from a register log. Edge Grinder's
349-second tune is 23,514 bytes as a compressed SN76489 log and **4,741 bytes
as Arkos tracker data** — and the replay is cheaper per frame than the log
player as well.

Nobody had done this on the BBC. Arkos ships 6502 players, but only for AKY
and only for machines with a real AY: Apple II with a Mockingboard, Oric,
Atari with a SONari. The BBC has an SN76489 and no AY at all, so every Arkos
player needs a conversion layer that did not exist anywhere.

## What is here

```
lib/ay2sn.asm       the spine: ay_regs -> SN76489            (BBC-specific)
lib/aklplayer.asm   AKL replay, hardware-free                (ours)
lib/akyplayer.asm   AKY replay, hardware-free                (ported, MIT)
example/            two demo discs, one per player
tools/              exporters, the verification harness, a WAV renderer
reference/          Arkos's own sources, vendored unmodified
```

Every player writes the fourteen AY registers into one buffer. `ay2sn`
converts that buffer to the SN76489, once a frame. Nothing else in the
library knows what machine it is on.

```
  aklplayer.asm ─┐
                 ├──►  ay_regs (14 bytes)  ──►  ay2sn.asm  ──►  &FE4F
  akyplayer.asm ─┘                                            (System VIA)
```

## Using it

Four things, and they are all `example/demo.asm` does:

```
ENV_BASE = 8                        \ 0. AKL only: the song's envelope pair.
                                    \    8 for almost every tune; see below
ORG &70
INCLUDE "lib/aklplayer.h.asm"       \ 1. the player's zero page (21 bytes;
                                    \    akyplayer.h.asm is 25)
...
INCLUDE "lib/ay2sn.asm"             \ 2. the spine, then the player
INCLUDE "lib/aklplayer.asm"
...
    lda #LO(song) : ldx #HI(song)   \ 3. once, with the exported data's
    ldy #0                          \    base (subsong index in Y; AKY
    jsr akl_init                    \    has no Y and parses its header)
...
.every_field                        \ 4. at the song's OWN replay rate,
    jsr akl_play                    \    from your VSync IRQ - see below
    jmp ay2sn
```

**`ENV_BASE` belongs to the song, not the player**, and `lib/aklplayer.asm`
deliberately does not default it — 8 is right for almost every tune, and a
tune whose real envelope AKL could not encode needs the pair shifted (EDGEA
needs 12). `tools/arkos.py` works it out from the song and
`example/build.py` passes it in, so the demo never gets it wrong.

**Call it at the rate the song was written for.** A song is authored for a
fixed number of replays a second and **the AKL and AKY exports do not carry
that number** — the player replays as often as you call it. Most Arkos songs
are 50 Hz, so a call per field is right. Some are not: Targhan's *Dead On
Time* is 25 Hz, and calling it every field plays it at exactly double speed,
in tune, with nothing at all to indicate a fault. `tools/verify/verify.py`
prints the rate, `tools/arkos.py` reads it, and `example/build.py` divides
the field rate by it.

`akl_silence` (in `ay2sn.asm`) is the four volume-off writes, for muting.
Mute **instead of** a frame of music, never as well as: running the player
and silencing the chip afterwards puts a burst of the tune's own volumes out
fifty times a second, and crackles.

Build the demo discs:

```
python example/build.py                 # build/ARKOS-AKL.SSD, ARKOS-AKY.SSD
python tools/verify/verify.py --player akl   # prove the player still works
python tools/make_tables.py --check          # prove the tables still match
```

Needs [beebasm](https://github.com/stardot/beebasm), `pip install py65 numpy`,
and an Arkos Tracker install to export songs and to be the oracle.

`tools/survey_tunes.py` sweeps a corpus — every song an Arkos install ships,
this repo's own, and EDGEA next door — and reports what each one stresses:
replay rate, PSG count, envelope use, how much falls below the chip's floor,
how often the bass changes channel. That is how the awkward cases here were
found, and it is worth running before trusting a figure measured on one
tune.

## Choosing a format

Edge Grinder's tune (`EDGEA.SKS`, 349 s), exported 2026-09-05 with Arkos
Tracker 3.7's own tools:

| format | bytes | 6502 player | cycles/field | notes |
|---|--:|---|--:|---|
| **AKM** | **3,654** | none anywhere | — | the successor to AKL. Z80 only |
| **AKL** | 4,741 | **`lib/aklplayer.asm`** | 2,320 mean, 3,378 max | **withdrawn upstream** |
| AKG | 4,956 | none anywhere | — | keeps the true envelope shape |
| **AKY** | 13,932 | **`lib/akyplayer.asm`** | 1,892 mean, 2,458 max | a register stream; cheapest CPU, largest data |
| VGC / VGI | 15,942 / 23,514 | [vgm-player-bbc](https://github.com/kieranhj/vgm-player-bbc) | 2,952 / 3,141 mean | pre-converted logs, for comparison |

Cycles are at 2 MHz, for the replay **and** the AY→SN conversion **and** the
chip writes — everything between the interrupt and the sound. Measured in
py65 over every frame of the tune by `tools/verify/verify.py`.

The code costs **3,300 bytes for AKL and 2,365 for AKY**, converter and
software bass included.

**Pick AKL if memory is tight, AKY if cycles are** — but read the next
section before picking AKL for anything new.

### Six-channel songs

A six-channel Arkos song carries two PSGs, and the BBC has one sound chip.
`aky_init` reads the channel count from the AKY header and steps the linker
by the whole entry, so **it plays the first PSG and ignores the rest** — no
preprocessing, no separate export. That is often exactly right rather than a
compromise: Arkos songs sometimes carry event data on a second PSG, and
Rhino's Acid Demo does.

### The bass

The SN76489's lowest note is 122 Hz, and between a third and nearly half of
every tune measured goes below it. `bass_mode` picks what happens to those
notes:

| `bass_mode` | | interrupts | costs |
|--:|---|---|---|
| **0** | shift them up an octave | none | the tune's bass line |
| **1** | **software bass**: park the channel's tone at an inaudible 125 kHz and bit-bang the note in the volume domain from a VIA timer — a real square wave | a VIA timer, 102–157 IRQ/s | nothing musical |
| **2** | **periodic noise**: the SN's noise generator with the feedback bit clear is a 1/15 duty pulse train clocked by tone generator 3, so tone 3's period sets the pitch and the whole bass register is in reach. This is what `ym2sn.py` does | **none** | the drums, while it plays |

Mode 1 is off until the host wires it up, because it needs an interrupt:

1. put **User VIA T1 in free-run** (ACR bit 6 set, bit 7 clear) so it
   reloads itself;
2. call `bass_irq` when User VIA T1 interrupts — and **test the flag against
   the enable**, `lda IFR : and IER : and #&40`. Masking a VIA interrupt does
   not stop its timer, so bit 6 goes on being set while T1 is disabled, and
   testing IFR alone services the bass on the back of every other interrupt
   in the machine. That mistake cost an afternoon: it made mute not mute and
   the bass crackle;
3. set `bass_mode` to 1.

Mode 2 needs none of that — `bass_mode = 2` and nothing else. It is the one
to reach for on a host that cannot spare a timer or cannot tolerate extra
interrupts, and it is **the only bass path the simulator can test**, since
py65 has no VIA. Leave `bass_mode` at 0 and the octave shift happens as
before. `example/demo.asm` cycles all three on the B key, and `akl_silence`
stops the bass as well as the four channels, so muting really mutes.

Which to choose is the drums against the interrupts. Mode 2 gives the voice
up whenever a drum wants the noise channel, which over the 75-song corpus
is **10% of the median song's bass calls** (mean 15%, seven songs above
40%); mode 1 never does. Against that, mode 2 costs no timer at all, and per
call it is only ~110 cycles dearer than mode 1 — which is less than mode 1's
interrupts cost on top.

**There is one voice either way**, and it is sticky — the channel holding it
keeps it while it still wants it, because choosing the lowest-numbered
claimant each call made it hop 25 times a second on a tune where two
channels play the same low note. One voice covers 99.5% of Rhino's
below-floor notes, 81.5% of EDGEA's and 78.7% of Dead On Time's, but over
the corpus **30 songs want three simultaneous bass voices and 26 want two**,
so it is a real limitation; the rest octave-shift as before.

The bass is only as steady as the interrupt latency — measured at about ±1%
within a note. See [`docs/fidelity-plan.md`](docs/fidelity-plan.md), which
also has the envelope fix and what is still open.

### AKL is withdrawn upstream

Arkos Tracker 3 ships no Lightweight player, no format documentation and no
`SongToLightweight.exe`, and the changelog does not mention removing them.
AKM's own documentation says why: *"This player may actually replace
Lightweight!"*

So:

- **`tools/export_akl.py` needs an Arkos Tracker 2 install, permanently.**
  AT3 cannot produce the format.
- AT2's AKL exporter can emit **data no player can play**. It exported a
  tune whose tracks reference arpeggio table 29 while writing a table with
  ten entries in it; Arkos's own Z80 player, read literally, walks off the
  end of the song exactly as ours does. `python tools/export_akl.py <song>
  --check` replays the export and refuses it if it does this. See
  [`docs/format-akl.md`](docs/format-akl.md).
- `reference/` keeps AT2's Lightweight sources and format spec, because
  nowhere else will.

AKL is nonetheless the proved player, the smallest combination measured, and
what Edge Grinder's `MUSIC_AKL` build uses. It is not going anywhere. But
**AKM is the format to port next**, and the README will say so until someone
does.

## What is verified, and against what

Nothing is checked against itself:

| | checked against | catches |
|---|---|---|
| `tools/verify/akl_reference.py` | `SongToYm.exe`'s register log — **Arkos's own full player**, same song | a misunderstanding of the format |
| `lib/aklplayer.asm` | that reference, frame for frame | a 6502 bug |
| `lib/akyplayer.asm` | the oracle directly (AKY is close to a register stream, so no transcription is needed) | both at once |
| the demo disc | the simulation, by capturing SN76489 writes in jsbeeb and finding them in it | a wiring, paging or interrupt bug |

Results as of 2026-09-05:

| player | tune | result |
|---|---|---|
| AKL | Targhan – Dead On Time (Ingame), 3,726 calls (**25 Hz**, 149 s) | 6502 identical to the reference; **no audible mismatch at all** |
| AKL | Targhan – Orion Prime L4 Theme 1 (50 Hz, 484 s) | 6502 identical to the reference; **no audible mismatch at all**. 72% of it is below the chip's floor — the hardest bass test of the 72 songs |
| AKL | EDGEA, 17,446 frames | 6502 identical to the reference; 11 channel-2 periods off by one |
| AKY | Rhino – Acid Demo 07, whole tune | **no audible mismatch at all** |
| AKY | Rhino – Acid Demo 21 (six channels) | **no audible mismatch at all** |
| AKY | EDGEA | periods differ as below; volumes differ, not yet explained |

Those eleven are **correct**, not a defect: Arkos documents a ±1 difference in
the volume/pitch effects between its PC side and its Z80 player.

**The oracle is version-sensitive, and this is worth knowing before you trust
a number.** The same EDGEA comparison gives 11 mismatches against Arkos
Tracker 2's `SongToYm.exe` and 791 against Arkos Tracker 3's — the 6502 is
byte-identical to the reference in both runs, so what changed is *Arkos's own
replay*, between AT2 and AT3. Say which oracle a figure came from.

## Prior art, and credit

Arkos Tracker is by **Julien Névo (Targhan/Arkos)** and everything here rests
on his work and his format documentation. The AKY player this one is derived
from is **Krzysztof Dudek (xxl)**'s Atari 8-bit port; there is a second 6502
AKY port for the Apple II and Oric by **Arnaud Cocquière (GROUiK/French
Touch)**. All MIT — see [`LICENSES/`](LICENSES/) and
[`LICENSES/PROVENANCE.md`](LICENSES/PROVENANCE.md) for exactly which file
came from where.

**The AY→SN76489 conversion is Simon Morris (simondotm)'s, and this is a
runtime implementation of it, not an independent one.**
[`ym2sn.py`](https://github.com/simondotm/ym2149f) is where the period
arithmetic, the volume mapping, the noise-rate matching, the periodic-noise
bass and the priority-channel idea all come from, expertly tuned over a long
time and against real ears; it is the reference this library is measured
against, frame by frame, by `tools/compare_streams.py`. The software bass
voice is his too, from `vgcplayer_bass.asm`. Where this library differs from
`ym2sn.py` it is because a per-frame converter cannot do whole-song
analysis - and where it agrees, it agrees exactly: on Rhino's Acid Demo 21
the runtime stream matches ym2sn's tone periods and noise byte on 100% of
audible frames.

What is new here is the AKL replay, the BBC port of the AKY replay, and
putting that conversion in the 6502 rather than in a build step. What is not
new is every idea underneath them.

The AKL work was built for the [Edge Grinder BBC
port](https://github.com/kieranhj/edge-beeb) and extracted from it.
`sn_write` comes from [vgm-player-bbc](https://github.com/kieranhj/vgm-player-bbc),
also Simon's.

## Documentation

- [`docs/format-akl.md`](docs/format-akl.md) — the format, the three
  conventions that had to be understood, and how the exporter can lie
- [`docs/ay-to-sn.md`](docs/ay-to-sn.md) — the conversion, and what a
  per-frame converter cannot do
- [`docs/verification.md`](docs/verification.md) — the oracle chain and how to
  re-run it
- [`docs/fidelity-plan.md`](docs/fidelity-plan.md) — the envelope and the
  two bass voices, what each cost, and the one question still open
- [`docs/porting.md`](docs/porting.md) — taking a replay to another 6502, or
  to a real AY
- [`PLAN.md`](PLAN.md) — where this came from and what is left
