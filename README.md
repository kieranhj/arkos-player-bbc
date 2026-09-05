# arkos-player-bbc

**Arkos Tracker music on the BBC Micro.** Three 6502 replays and the
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

**`lib/akmplayer.asm` is the only 6502 AKM player there is**, on any machine.
AKM is Arkos's smallest format and its documented successor to Lightweight;
until now it was Z80 only.

## Listen to it

Both demo discs run in the browser, on a stock Model B — no second processor,
no sideways RAM, nothing but a BBC Micro and its sound chip:

- **[AKM — Targhan, *Crtc*](https://bbc.xania.org/?disc=https://bitshifters.github.io/content/wip/arkos-akm-wip.ssd&autoboot&model=B)**
- **[AKY — Rhino, *Acid Demo*](https://bbc.xania.org/?disc=https://bitshifters.github.io/content/wip/arkos-aky-wip.ssd&autoboot&model=B)**

**SPACE** mutes, **B** cycles the bass through periodic noise, the software
voice and none at all, **ESCAPE** quits. The red band is the music: what you
are looking at is the cost of the frame you are listening to.

*Crtc* is the tune to judge the AKM player by, and it was picked by
measurement rather than taste — of the 75 songs `tools/survey_akm.py` sweeps
it reaches 21 of the player's 26 code paths, more than any other. It also
leans hard on notes below the SN76489's 122 Hz floor, so **B** is worth
pressing: that is the whole argument of [`docs/ay-to-sn.md`](docs/ay-to-sn.md)
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

Every player writes the fourteen AY registers into one buffer. `ay2sn`
converts that buffer to the SN76489, once a frame. Nothing else in the
library knows what machine it is on.

```
  aklplayer.asm ─┐
  akmplayer.asm ─┼──►  ay_regs (14 bytes)  ──►  ay2sn.asm  ──►  &FE4F
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
python example/build.py                 # ARKOS-AKL / -AKY / -AKM .SSD
python example/build.py --extra         # build/ARKOS-EDGEA.SSD, ARKOS-ORION.SSD
python tools/verify/verify.py --player akl   # prove the player still works
python tools/verify/akm_verify_corpus.py     # prove AKM on all 39 of its songs
python tools/make_tables.py --check          # prove the tables still match
python tools/compare_formats.py              # the size/cost table below
```

Five discs, and the last two are test cases rather than demos. **EDGEA** is
the tune the library was built for and the only one here that uses the
hardware envelope. **Orion Prime Level 4** is the hardest bass of the 75
songs surveyed: 69% of its audible channel-frames are below the chip's
floor and 54% of its bass calls want two voices at once, so it is where a
one-voice bass shows its limit. Both play through `lib/aklplayer.asm`.
`--song` with `--disc` builds any other song the same way without
overwriting a demo.

The **AKM** disc plays Targhan's *Crtc* - see [Listen to it](#listen-to-it) -
and that tune was picked by measurement rather than taste: of the 75 songs
`tools/survey_akm.py` sweeps, it reaches 21 of the player's 26 paths,
including the pitch table and two of the force-speed effects, three paths AKL
has still never executed.

The AKM and AKY discs are published as WIP builds and are the two links at the
top; `tools/verify/find_capture.py` is how a disc is proved to write what the
simulation says it should.

All five **default to the periodic-noise bass** (`bass_mode 2`), because it
is the one a host can have without giving up a timer or taking on
interrupts. B cycles to the software voice and to no bass at all, which is
the comparison worth making by ear.

Needs [beebasm](https://github.com/stardot/beebasm), `pip install py65 numpy`,
and an Arkos Tracker install to export songs and to be the oracle.

`tools/survey_tunes.py` sweeps a corpus — every song an Arkos install ships,
this repo's own, and EDGEA next door — and reports what each one stresses:
replay rate, PSG count, envelope use, how much falls below the chip's floor,
how often the bass changes channel. That is how the awkward cases here were
found, and it is worth running before trusting a figure measured on one
tune.

## Choosing a format

Six ways to get a song out of an SN76489, over the four tunes on the demo
discs. Every figure is measured, none is quoted from anywhere else, and
`python tools/compare_formats.py` regenerates the lot into `build/formats.md`.

Cycles are **one player call including its SN76489 writes**, simulated in
py65 at 2 MHz. A call is a frame of music, so a 25 Hz song like *Dead On
Time* is called half as often and costs half as much a second as its row
suggests. RAM is the tune plus the player's code plus its workspace — the
whole cost of having the music in the machine.

### Rhino, Acid Demo 21 — 192 s, 50 Hz, 9,600 calls

| format | tune | + player & workspace | = RAM | mean | max |
|---|--:|--:|--:|--:|--:|
| AKL | 5,270 | — | — | — | — |
| **AKY** | 11,713 | 2,677 | **14,390** | 2,228 | 2,739 |
| **AKM** | 7,092 | 4,161 | **11,253** | 2,657 | 4,734 |
| AKG | 8,674 | no player | — | — | — |
| **VGC** | 7,460 | 2,816 | **10,276** | 1,711 | **5,321** |
| **VGI** | 10,069 | 3,584 | **13,653** | 1,551 | 2,652 |
| VGM (unpacked) | 84,249 | no player | — | — | — |

AT2 exports an AKL for this tune and it **will not play** — the arpeggio
fault in [`docs/format-akl.md`](docs/format-akl.md). This is the tune the
AKY disc uses, and why.

### Targhan, Dead On Time — 149 s, 25 Hz, 3,726 calls

| format | tune | + player & workspace | = RAM | mean | max |
|---|--:|--:|--:|--:|--:|
| **AKL** | **1,988** | 3,612 | **5,600** | 2,683 | 3,686 |
| **AKY** | 5,686 | 2,677 | 8,363 | 2,343 | 2,771 |
| **AKM** | **1,741** | 4,161 | 5,902 | 2,775 | 4,267 |
| AKG | 2,074 | no player | — | — | — |
| **VGC** | 5,950 | 2,816 | 8,766 | 2,034 | **5,430** |
| **VGI** | 6,460 | 3,584 | 10,044 | 1,578 | 2,726 |
| VGM (unpacked) | 39,493 | no player | — | — | — |

### Tom&Jerry, Edge Grinder — 349 s, 50 Hz, 17,446 calls

| format | tune | + player & workspace | = RAM | mean | max |
|---|--:|--:|--:|--:|--:|
| **AKL** | 4,741 | 3,612 | 8,353 | 2,693 | 3,873 |
| **AKY** | 13,932 | 2,677 | 16,609 | 2,270 | 2,854 |
| **AKM** | **3,654** | 4,161 | **7,815** | 2,746 | 4,463 |
| AKG | 4,956 | no player | — | — | — |
| **VGC** | 14,702 | 2,816 | 17,518 | 1,485 | **5,546** |
| **VGI** | 22,292 | 3,584 | 25,876 | 1,566 | 3,004 |
| VGM (unpacked) | 128,027 | no player | — | — | — |

### Targhan, Orion Prime L4 — 484 s, 50 Hz, 24,192 calls

| format | tune | + player & workspace | = RAM | mean | max |
|---|--:|--:|--:|--:|--:|
| **AKL** | 2,320 | 3,612 | 5,932 | 2,712 | 3,889 |
| **AKY** | 5,741 | 2,677 | 8,418 | 2,366 | 2,953 |
| **AKM** | **1,755** | 4,161 | **5,916** | 2,751 | 4,541 |
| AKG | 2,368 | no player | — | — | — |
| **VGC** | 5,841 | 2,816 | 8,657 | 1,002 | **5,601** |
| **VGI** | 10,530 | 3,584 | 14,114 | 1,509 | 2,863 |
| VGM (unpacked) | 100,445 | no player | — | — | — |

### What that says

**AKL is the smallest way to have music on a BBC**, and not by a little: on
every tune where its export is sound it wins total RAM by 1.4× to **2.0×**,
and the longer the tune the wider the gap — 8,336 bytes against VGI's 25,876
for Edge Grinder's 349 seconds. A tracker replay stores the *song*; a
register log stores the *output*, and output grows with length while a song
mostly does not. Orion Prime is 484 seconds in 2,320 bytes.

**VGI is the cheapest and by far the steadiest**, 1,509–1,578 cycles mean on
every tune and never past 3,004. **VGC has the lowest mean of anything here**
— 1,002 on Orion — and spikes to 5,321–5,601 on all four, which is the number
that matters on a raster-timed host: it is the frame that tears. Our two are
in between and flat, AKY's worst frame (2,732–2,948) beating AKL's
(3,682–3,886) because AKY does almost nothing per frame and `ay2sn` becomes
the whole cost.

**AKM is the smallest data of all, and now it has a player** —
`lib/akmplayer.asm`, the only 6502 AKM replay in existence. Its tune data
beats AKL on every song here: 3,654 bytes against 4,741 on Edge Grinder,
1,741 against 1,988 on Dead On Time.

**It does not follow that AKM is the better choice, and the tables above say
so.** Its player is 4,161 bytes against AKL's 3,612 — most of the difference
a period table with 256 entries where AKL's has 128, because AKM's note index
is 8-bit and wraps. So on **total** RAM AKM wins only where the tune is long
enough to pay for that: 538 bytes better on Edge Grinder's 349 seconds, 16
bytes better on Orion's 484, and 302 bytes **worse** on Dead On Time's 149.

**And it is dearer per call, exactly as Targhan says it should be.** His
player header warns AKM is *"much slower than the generic one or the AKY
player"*; on a 6502 it costs 39–92 cycles a call more than AKL, and its worst
frame is 400–850 cycles worse — which is the number that matters on a
raster-timed host. The tail is where its decoding cleverness lands: a line
that reads a new track cell on all three channels does more work than
Lightweight's did.

So **AKM for a long tune, AKL for a short one**, and read the max column
before either. See [`docs/format-akm.md`](docs/format-akm.md).

AKG remains without a 6502 player anywhere.

Two things the numbers do not say on their own. Our cycle figures **include
the whole AY→SN conversion and the bass voice**, computed every call; VGC and
VGI get all of that for free because `ym2sn.py` did it offline, hours before,
with whole-song analysis — the trade this library exists to make, and
[`docs/ay-to-sn.md`](docs/ay-to-sn.md) says how close it now gets. And VGI's
3,584 bytes of workspace are eleven 256-byte ring windows that must be page
aligned, where AKL and AKY want 22 bytes of zero page and nothing else.

**So: AKL or AKM if memory is tight — AKM once the tune is long enough to pay
for its bigger player — AKY if cycles are, VGI if you have the RAM and need a
flat worst case.** Read the next section before picking AKL for anything new.

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

### AKM has two things AKL has not

**A second oracle.** `SongToAkm.exe` without `-bin` writes the song as
assembler source with a comment on every byte saying what it means, so
`tools/verify/akm_source_check.py` can hold the reference's decode against
Arkos's own statement of it — cell by cell, rather than waiting for a register
log to show a fault hundreds of frames after its cause. **74 songs, 48,201
checks, zero disagreements.** AKL has no equivalent and would be easier to
finish if it did.

**A documented open question.** On 25 of the 64 CPC-clock corpus songs the
reference and Arkos's replay still differ, in the *rendering* rather than the
decode — the annotation oracle rules the decode out. `lib/akmplayer.asm` is
verified on the other 39, which are listed in
`tools/verify/akm_known_good.txt`, and the whole thing is written up in
[`docs/akm-open-questions.md`](docs/akm-open-questions.md) along with the
eleven Atari ST and MSX tunes, which need only a different period table and
include the corpus's only user of SoftAndHard.

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

AKL is nonetheless a proved player and what Edge Grinder's `MUSIC_AKL` build
uses, and it is not going anywhere — on a short tune it still beats AKM on
both RAM and cycles. But **it is the format with no future**, so anything new
should start with AKM, which needs no AT2 install and whose data is smaller on
every tune measured.

**AKG is now the only Arkos format with no 6502 player anywhere.** It carries
the true envelope shape, so it would need no `ENV_BASE` compensation at all —
which is the one fidelity gap AKL and AKM share.
[`docs/porting.md`](docs/porting.md) is the route.

## What is verified, and against what

Nothing is checked against itself:

| | checked against | catches |
|---|---|---|
| `tools/verify/akl_reference.py` | `SongToYm.exe`'s register log — **Arkos's own full player**, same song | a misunderstanding of the format |
| `lib/aklplayer.asm` | that reference, frame for frame | a 6502 bug |
| `tools/verify/akm_reference.py` | **Arkos's own byte-by-byte annotation** of the same data, as well as `SongToYm.exe` | a misunderstanding of the format, ON THE CELL that caused it |
| `lib/akmplayer.asm` | that reference, frame for frame, over 39 songs | a 6502 bug |
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
runtime implementation of it, not an independent one.** Close enough now
that on a tune with no hardware envelope it is not an approximation of his
output at all - it *is* his output, every tone period, tone volume and
noise byte, over all 9,600 calls of Rhino's Acid Demo.
[`ym2sn.py`](https://github.com/simondotm/ym2149f) is where the period
arithmetic, the volume mapping, the noise-rate matching, the periodic-noise
bass and the priority-channel idea all come from, expertly tuned over a long
time and against real ears; it is the reference this library is measured
against, frame by frame, by `tools/compare_streams.py`. The software bass
voice is his too, from `vgcplayer_bass.asm`. Where this library still differs from
`ym2sn.py` it is because a per-frame converter cannot do whole-song
analysis: the hardware envelope, and the loudness of the drums.

What is new here is the AKL replay, the BBC port of the AKY replay, and
putting that conversion in the 6502 rather than in a build step. What is not
new is every idea underneath them.

The AKL work was built for the [Edge Grinder BBC
port](https://github.com/kieranhj/edge-beeb) and extracted from it.
`sn_write` comes from [vgm-player-bbc](https://github.com/kieranhj/vgm-player-bbc),
also Simon's.

## Documentation

**The formats**

- [`docs/format-akl.md`](docs/format-akl.md) — AKL, the three conventions that
  had to be understood, and how its exporter can lie
- [`docs/format-akm.md`](docs/format-akm.md) — AKM, why it needs its own period
  table, and the V0-player/V1-exporter split in Arkos Tracker 3

**The conversion, and how any of it is known to work**

- [`docs/ay-to-sn.md`](docs/ay-to-sn.md) — the conversion, and what a
  per-frame converter cannot do
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
