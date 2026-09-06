# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project overview

**Arkos Tracker music on the BBC Micro**: three 6502 replays (AKL, AKM, AKY) and the
AY-3-8912 → SN76489 layer they need on a machine with no AY at all. It was extracted from the
Edge Grinder BBC port (`../edge-beeb`, its `MUSIC_AKL` build) on 2026-09-05 and is now upstream
of it.

`lib/akmplayer.asm` is **the only 6502 AKM player there is**, on any machine. Arkos ships 6502
players only for AKY, and only for hosts with a real AY (Apple II + Mockingboard, Oric, Atari +
SONari).

The live documents, in the order to read them:

- **`PLAN.md`** — what is left, and nothing else. Every item has an acceptance test. Read it first.
- **`docs/decisions.md`** — KC's decisions, binding, plus four standing rules that are not numbered.
- **`README.md`** — what it is, the API, and every measured table (size, cycles, verification
  results). Long, and the place a figure is quoted from.
- **`docs/history.md`** — how it got built, and what the plan got wrong on the way.

## Working approach

**Nothing is believed without an acceptance test.** Every figure in every document says what it
was measured on and when; a change that moves a figure moves the document with it.

**Say which oracle a number came from.** AT2's `SongToYm.exe` and AT3's disagree about the same
song — the EDGEA comparison gives 11 audible mismatches against one and 431 against the other,
with the 6502 byte-identical to its reference in both runs. What changed is *Arkos's own replay*.
`verify.py` prefers AT3 and prints which it used.

**Nothing is checked against itself.** The chain is: a Python transcription of Arkos's own Z80
player against a `.ym` register log from `SongToYm.exe` (catches a misunderstanding of the
format); the 6502 against that transcription in py65, frame for frame on `ay_regs` (catches a
6502 bug); the demo disc against the simulation, by capturing SN76489 writes out of jsbeeb and
finding them in the simulated stream (catches a wiring, paging or interrupt bug — the one class
everything upstream is blind to, since it all runs in a simulator). `docs/verification.md`.

**Do not write hardware code from recalled facts.** The jsbeeb MCP is configured for this project
(`.mcp.json`): set the registers, run the disc, read the memory or the sound state back, confirm,
then build on it. The IFR/IER rule below is what recalling instead costs.

**A path nothing has ever called is not a tested path.** Five of AKL's seven effects have still
never executed, and AKM's `SoftAndHard` never has. `tools/survey_akm.py` exists so a player can
at least say which of its paths its testing reached.

**Deviations from `docs/decisions.md` are agreed with KC before they are built and written down
after**, as a numbered row there. Do not quietly substitute a design of your own.

**Do not redistribute the Arkos exporters** — the MIT sentence covers the *players*. The tunes in
`songs/` are not MIT either: they are used by permission of their composers (`songs/README.md`),
and a fork takes the code and not the music. Anything vendored gets a row in
`LICENSES/PROVENANCE.md` saying where it came from and under what terms.

## The library

```
lib/ay2sn.asm       the spine: ay_regs -> SN76489            (BBC-specific)
lib/aklplayer.asm   AKL replay, hardware-free                (ours)
lib/akmplayer.asm   AKM replay, hardware-free                (ours; the only one)
lib/akyplayer.asm   AKY replay, hardware-free                (ported from xxl's Atari port, MIT)
example/            the demo, and five discs built from it
tools/              exporters, the verification harness, a WAV renderer
reference/          Arkos's own sources, vendored unmodified — do not edit
songs/              two Rhino tunes, by permission; not MIT
LICENSES/           every vendored file's origin and terms
```

Every player writes the fourteen AY registers into one buffer; `ay2sn` converts that buffer to the
SN76489, once a frame. **`ay_regs` is the boundary and it is load-bearing**: no player may know
what machine it is on (decision 1), so a replay alone travels to an Oric or an Apple II.

The API is three symbols per player — `akl_init` (A/X = lo/hi of the song, Y = subsong index),
`akl_play` (one frame, fills `ay_regs`), and `ay_regs` itself; `aky_init` takes A/X = the
subsong linker and no Y, parsing its own header. The `.h.asm` files are the zero page each needs
(AKL 22 bytes, AKY and AKM 25), INCLUDEd inside the host's own ZP block at whatever address suits
— except that **AKY's 25 must stay in the order given**, because the player indexes across them.

Two things a host gets wrong silently, both written up in the README:

- **`ENV_BASE` belongs to the song, not the player**, and is deliberately never defaulted
  (decision 9). 8 is right for almost every tune; EDGEA needs 12. `tools/arkos.py`'s
  `envelope_base()` works it out and `example/build.py` passes it in.
- **Call the player at the rate the song was written for.** The AKL and AKY exports do not carry
  it. Most Arkos songs are 50 Hz; Targhan's *Dead On Time* is 25, and calling it every field plays
  it at exactly double speed, in tune, with nothing in the register stream to indicate a fault.
  **The frame-for-frame checks cannot catch this** — they compare call for call. `tools/arkos.py`
  reads the rate out of a `SongToYm.exe` YM header, the only place it is written down.

`akl_silence` (in `ay2sn.asm`) mutes **instead of** a frame of music, never as well as: running
the player and silencing the chip afterwards puts a burst of the tune's own volumes out fifty
times a second, and crackles.

## Build and verify

Run everything **from the repo root** — beebasm resolves `INCLUDE`/`INCBIN` from the working
directory. Needs beebasm, `pip install py65 numpy`, and an Arkos install to export songs and to
be the oracle. Without an oracle `verify.py` still runs the 6502-against-reference check and says
which check it skipped.

```
python example/build.py                        # build/ARKOS-AKL / -AKY / -AKM .SSD
python example/build.py --extra                # ARKOS-EDGEA.SSD, ARKOS-ORION.SSD
python example/build.py --song X.aks --disc D  # any other song, without overwriting a demo
python tools/verify/verify.py --player akl     # 6502 vs reference vs oracle
python tools/verify/akm_verify_corpus.py       # AKM on all 39 known-good songs
python tools/make_tables.py --check            # the generated tables still match their source
python tools/compare_formats.py                # regenerates the README's tables into build/formats.md
python tools/sn2wav.py build/x.snf -o build/x.wav
```

`build/` is gitignored and holds everything generated. beebasm is `../../Bin/beebasm.exe`; a local
`bin/beebasm.exe` wins if present (`bin/` is gitignored too).

Arkos installs are found through `ARKOS3_HOME` / `ARKOS2_HOME`, defaulting to
`~/OneDrive/Trackers/ArkosTracker3` and `~/OneDrive/Trackers/Arkos Tracker 2`.
**`tools/export_akl.py` needs an AT2 install permanently**: AT3 has withdrawn Lightweight — no
player, no documentation, no `SongToLightweight.exe` — which is why `reference/` keeps AT2's
sources and spec, nowhere else having them.

The demo runs on a **stock Model B**: no second processor, no sideways RAM. MODE 6, IRQ1V taken,
the song assembled at `&3000` under `GUARD &6000` (where MODE 6's screen starts). SPACE mutes,
B cycles the bass through periodic noise / software voice / none, ESCAPE quits; the red band is
the cost of the frame you are listening to.

**The jsbeeb MCP is configured for this repo** in `.mcp.json` (project scope — the first session
in a new checkout is asked to approve it), the same server `../edge-beeb` uses. Boot the demo
discs on it as a **Model B**, not a Master: they are built for a stock machine, and a fault that
only shows on one model is exactly what this step is for. The disc-against-simulation check has
so far been run by pasting a jsbeeb sound capture into a file and searching for it in the
simulated stream:

```
python tools/verify/verify.py --player akm --song X.aks --bass 2 --snf build/sim.snf
python tools/verify/find_capture.py build/capture.txt build/sim.snf
```

## Facts that cost time to learn

- **Test a VIA interrupt flag against the enable**: `lda IFR : and IER : and #&40`. Masking a VIA
  interrupt does not stop its timer, so bit 6 goes on being set while T1 is disabled, and testing
  IFR alone services the bass on the back of every other interrupt in the machine. It made mute
  not mute, and the bass crackle.
- **The System VIA's T1 is the MOS's 100 Hz tick.** Taking it breaks the OS; the demo's software
  bass uses a User VIA timer, in free-run (ACR bit 6 set, bit 7 clear).
- **AT2's AKL exporter can emit data no player can play**: tracks referencing arpeggio table 29
  when it wrote ten. Arkos's own Z80 player, read literally, walks off the end of the song exactly
  as ours does. `python tools/export_akl.py <song> --check` replays the export and refuses it.
  The same exporter squashes a six-channel song into three without a word of warning.
- **The AKM period table cannot be shared with AKL's** (decision 7). AKM derives its periods at
  run time by halving twelve octave-0 entries, and that disagrees with Arkos's own 128-note table
  on six notes. `make_tables.py` generates it from AKM's own arithmetic — 256 entries, because the
  note index is 8-bit and wraps.
- **AKM is smaller data but a bigger player** (4,161 bytes against AKL's 3,612, most of it that
  period table) and 39–92 cycles a call dearer, with a worst frame 400–850 cycles worse. So AKM
  for a long tune, AKL for a short one, and read the max column before either. "AKM beats AKL" was
  believed at the start and is wrong as stated.
- **There is one bass voice and it is sticky.** Choosing the lowest-numbered claimant each call
  made it hop 25 times a second on a tune where two channels play the same low note. Over the
  75-song corpus 30 songs want three simultaneous bass voices and 26 want two, so it is a real
  limitation, written up in `docs/fidelity-plan.md`.
- **`bass_mode 2` (periodic noise) is the default on all five discs**, because it is the one a host
  can have without giving up a timer or taking on interrupts — and it is the only bass path the
  simulator can test, py65 having no VIA.
- A six-channel Arkos song carries two PSGs and the BBC has one sound chip. `aky_init` reads the
  count out of the header and plays the first, ignoring the rest. That is often right rather than
  a compromise: Rhino's Acid Demo rides event data on its second PSG.

## Conventions

- BeebASM syntax: labels `.name`, comments `\`, hex `&`. Each `lib/` file opens with a boxed `\ *`
  header stating what it is and the facts behind it; keep that.
- `lib/akl_periods.asm`, `lib/akm_periods.asm` and `lib/ay2sn_tables.asm` are **generated** by
  `tools/make_tables.py` and committed. Regenerate rather than edit; `--check` proves they still
  match their source.
- Python tools carry a docstring saying what the tool is for and what it caught. That is where the
  hard-won facts live, and a new one belongs there rather than in a commit message.
- Keep names matching Arkos's own where a routine is a transcription of one.
