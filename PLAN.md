# arkos-player-bbc — the plan

**Status: planned, not started. 2026-09-05.** Nothing exists in this repo yet but this file.

Arkos Tracker replays for the BBC Micro, with the AY-3-8912 → SN76489 layer they need in order to
play on a machine the format was never meant for. Extracted from the Edge Grinder port
(`BEEB/Repos/edge-beeb`, `MUSIC_AKL`), where the AKL player was built, proved and parked.

Sits beside `vgm-player-bbc` and follows its shape: `lib/`, `docs/`, a demo `.asm` and `.ssd`,
an MIT `LICENSE`.

**Name**: `arkos-player-bbc`, chosen to match `vgm-player-bbc`. Not final.

---

## Why this is worth a repo

A tracker replay is a different trade from a register log. The whole 349 seconds of Edge Grinder's
tune is 23,514 bytes as a `.vgi` and **4,741 bytes as AKL tracker data** — and the AKL replay is the
cheapest player ever measured on this project, 2,183 cycles a frame against VGI's 3,141.

Nobody has done this on the BBC. Arkos ships 6502 players, but only for AKY and only for machines
with a real AY (Apple II + Mockingboard, Oric, Atari + SONari). The BBC has an SN76489 and no AY at
all, so every Arkos player needs a conversion layer that does not exist anywhere else.

## Licences — checked, and clean

- **Arkos Tracker 3 ships `LICENSE.txt`**: MIT, "Copyright (c) 2016-2025 Julien Nevo
  (contact@julien-nevo.com)". AT2 had no licence file; the terms were only on the website FAQ
  ("*Of course! The players are MIT-licensed... in any production, free or sold, open or closed
  source*"). Vendor the AT3 file; archive the FAQ wording beside it for the AT2-era sources.
- **The 6502 AKY ports carry their own MIT licences**: Apple II / Oric by Arnaud Cocquière
  (GROUiK/French Touch), 2019. Atari 8-bit by Krzysztof Dudek (xxl), 2021.
- **The `SongTo*.exe` exporters are not covered by that sentence** — it says *players*. Do not
  redistribute them. Require an Arkos install and take the path from config, the way
  `edge-beeb`'s `tools/export_music_akl.py` already does.
- Crediting Arkos is non-mandatory and we will do it anyway, prominently.

## The formats, measured

All figures are Edge Grinder's tune (`source_cpc/Music/EDGEA.SKS`, 349 s, by Tom & Jerry), exported
2026-09-05 with AT3 3.7's own tools. AT3 loads `.SKS` directly.

| format | bytes | 6502 player | status |
|---|--:|---|---|
| **AKM** | **3,654** | none anywhere | the successor. Z80 only. Same envelope 8/10 limit as AKL |
| **AKL** | 4,741 | **ours** | **withdrawn from AT3** — see below |
| AKG | 4,956 | none anywhere | keeps the true envelope 12, so no `ENV_BASE` hack |
| **AKY** | 13,932 | **upstream, MIT** | a register-block stream; near-zero CPU, large data |
| VGC / VGI | 15,942 / 23,514 | ships in edge-beeb | for comparison |

### AKL is withdrawn upstream

AT3 3.7 has no `playerLightweight` and no `SongToLightweight.exe`, and the changelog does not
mention removing them. AKM's own doc says why: *"This player may actually replace Lightweight!"*

Consequences, both to be stated plainly in the README rather than discovered by a user:

- **The AKL export chain requires an Arkos Tracker 2 install, permanently.** AT3 cannot produce the
  format.
- The AKL player is nonetheless the proved one, is byte-identical to Arkos's own output over all
  17,446 frames of the reference tune, and is the smallest-and-cheapest combination measured. It
  ships as-is; AKM is the documented upgrade path.

## The design: `ay_regs` is the spine

Every player writes the fourteen AY-3-8912 registers into one buffer. `ay2sn.asm` converts that
buffer to the SN76489, once a frame. Nothing else in the library knows about the BBC.

```
  aklplayer.asm  ─┐
  akyplayer.asm  ─┼──►  ay_regs (14 bytes)  ──►  ay2sn.asm  ──►  sn_write  ──►  &FE4F
  (akmplayer)    ─┘                                                (System VIA)
```

This is not a retrofit — `aklplayer.asm` was written to that boundary from the start, deliberately,
so that the replay and the conversion could be measured separately. It is what makes a
multi-player library cheap, and it is what makes one verification harness serve every player.

## Layout

```
arkos-player-bbc/
  README.md                 what it is, the format table, cost, API, traps, credits
  LICENSE                   MIT (ours)
  LICENSES/
    arkos-tracker.txt       AT3's LICENSE.txt, verbatim
    arkos-faq-at2.md        the AT2-era website wording, archived with its URL and date
    aky-6502-apple-oric.txt Arnaud Cocquière, 2019
    aky-6502-atari.txt      Krzysztof Dudek, 2021
    PROVENANCE.md           every vendored file: where from, which Arkos version, which licence
  lib/
    ay2sn.asm               the spine: ay_regs -> SN76489, sn_write, silence   (BBC-specific)
    ay2sn_tables.asm        generated
    aklplayer.asm           AKL replay, hardware-free                          (ours)
    aklplayer.h.asm         ZP block, API, ENV_BASE and the config constants
    akyplayer.asm           AKY replay, hardware-free                          (ported)
    akyplayer.h.asm
  example/
    demo.asm                one disc, both players, mute/pause, raster-bar cost meter
    build.ps1 / build.sh    beebasm only; no ZX0, no loader
  tools/
    export_akl.py           SKS/AKS -> .akl at an address     (needs an AT2 install)
    export_aky.py           any song -> .aky at an address    (AT3)
    make_tables.py          NEW - generates lib/ay2sn_tables.asm
    sn2wav.py               .snf / .vgm -> WAV, for listening
    verify/
      akl_reference.py      the Python transcription of PlayerLightweight.asm
      aky_reference.py      the same for AKY
      sim.asm               the real lib/ sources with a ZP block and an ORG
      verify.py             build, simulate, diff against the oracle, report cost
  reference/                vendored, unmodified, for study
    PlayerLightweight.asm             AT2, Z80 — the ancestor of lib/aklplayer.asm
    SongLightweightExportFormat.md    AT2 — the AKL format spec
    PlayerAky.asm                     AT3, Atari MADS — the ancestor of lib/akyplayer.asm
    PlayerAKY_6502.a                  AT3, Apple/Oric ACME — the other 6502 AKY port
    AKY.md, AKM.md, AKG.md            AT3 format specs
  songs/                    the demo tune, its exports, and its licence note
  docs/
    format-akl.md           what AKL is, and the three conventions that had to be understood
    format-aky.md
    verification.md         the oracle chain, and why 11 ch2-period diffs is a PASS
    cost.md                 the measured tables, simulated and in-game
    ay-to-sn.md             the conversion, and what a per-frame converter cannot do
    porting.md              taking a replay to a non-BBC 6502, or to a real AY
```

## Steps

Each step has an acceptance test. Nothing is believed without one.

### 1. Repo, licences, vendored reference

`git init`, MIT `LICENSE`, `LICENSES/` and `PROVENANCE.md` complete, `reference/` populated
unmodified. Vendor the AT2 Lightweight sources **especially** — AT3 has deleted them and nowhere
else will keep them.

*Accepts when*: every file in `reference/` and `lib/` has a row in `PROVENANCE.md` naming its
origin, its Arkos version and its licence.

### 2. Lift AKL and `ay2sn`

Copy `src/aklplayer.asm` and `src/ay2sn.asm` from edge-beeb. Split the 22-byte zero-page block out
of edge-beeb's `main.asm` into `lib/aklplayer.h.asm` — the pattern `vgm-player-bbc` already uses for
`vgiplayer.h.asm`. Make `ENV_BASE` and the song address parameters of the header rather than
constants buried in the body. Fix the `INCLUDE` paths.

*Accepts when*: `python tools/verify/verify.py --player akl` prints, in this repo,
`IDENTICAL on every frame` and `audible mismatches: {'ch2 period': 11}` over all 17,446 frames.
That eleven is the correct answer, not a defect — it is Arkos's own documented ±1 in the
volume/pitch effects between the PC side and the Z80 player.

### 3. `make_tables.py`

`src/data/akl_ay2sn_tables.asm` is committed to edge-beeb with **no generator anywhere in the
repo**: the 32-entry volume LUT, the envelope shape table and the 256-entry reciprocal table cannot
currently be reproduced or re-derived. A library cannot ship that.

*Accepts when*: `python tools/make_tables.py` regenerates `lib/ay2sn_tables.asm` byte for byte
identical to edge-beeb's committed copy.

### 4. Port AKY

Take **xxl's Atari version** (`PlayerAky.asm`, 658 lines, MADS), not the Apple/Oric one (1,306
lines, ACME) — it is half the size and its entire hardware coupling is two constants and one
register write. Convert MADS syntax to BeebASM, and redirect the register writes into `ay_regs`
instead of a chip, then call `ay2sn` once at the end of the frame.

*Accepts when*: `python tools/verify/verify.py --player aky` matches `SongToYm.exe`'s output for
the same song, on the same terms as AKL — audibly identical, with every difference explained.

Note the trade: AKY does so little work per frame that `ay2sn` becomes the dominant cost. That
makes it the stress test for the conversion layer and a genuinely useful row in `cost.md`.

### 5. The demo disc

A plain SSD — no ZX0, no loader, player in main RAM, its own VSync IRQ. Both players selectable.
Keys for mute and pause. A palette-write raster bar so the cost is **visible** on screen.

The tune is one of **Targhan's own songs bundled with the tracker** — `Dead On Time - Ingame` or
`Midline Process - Molusk`, the two Arkos itself uses as the Lightweight player's test music. That
settles the redistribution question, and it exercises player paths EDGEA never touched (see Traps).
Confirm with Targhan in the same mail as the licence courtesy.

*Accepts when*: it boots in jsbeeb, plays, and the raster bar's height matches the simulated cost.

### 6. README and docs

The format table above, the measured costs, the API, the credits, and the traps stated loudly
rather than buried.

### 7. Then the fidelity work

Now that it lives in `ay2sn`, both known gaps benefit every player at once:

1. **Noise rate 3 — the tuned noise.** `ym2sn.py` clocks the SN's noise from tone generator 3 on
   1,701 of its frames, which is how it gets a pitched drum and a bass out of the noise channel.
   `ay2sn.asm` never emits rate 3 at all. Largest remaining difference on percussion.
2. **Average the envelope across the frame instead of sampling it once.** It drives a channel's
   volume on 33% of the tune, every envelope runs at 1.2–2.9 complete cycles per frame, and
   `ym2sn` low-passes where we take one sample — which is why envelope frames agree on only 3.6%
   of tone periods. A closed-form average of a saw over a window; a couple of hundred cycles.

Then render everything to WAV side by side and listen.

## Decisions taken (KC, 2026-09-05)

1. **Scope**: replay + AY→SN, BBC-framed — but `aklplayer.asm`/`akyplayer.asm` stay strictly
   hardware-free with a documented `ay_regs` boundary, so the replay alone travels to an Oric or an
   Apple II.
2. **Demo tune**: an Arkos-bundled Targhan song, not EDGEA (third-party, and it exercises the
   least).
3. **Timing**: extract now, finish the fidelity work here rather than in edge-beeb.
4. **edge-beeb's copy**: becomes a verbatim copy in its `lib/`, the same treatment as
   `lib/vgiplayer.asm`. The library is upstream; edge-beeb never edits it.
5. **AKM**: noted now, ported later. v1 is AKL + AKY. AKM is the documented upgrade path and the
   obvious next player — 3,654 bytes and upstream-supported, but a second from-scratch port of a
   Z80 replay, i.e. the same size of job AKL was.
6. **Edge Grinder**: stays on VGI. `MUSIC_AKL` remains the parked comparison build and decision 40
   stays open. Fidelity work here can feed back if and when KC's ear says so.

## Traps, carried over from edge-beeb

- **`ENV_BASE` lives in two places** — the player and `akl_reference.py` — and they must agree, or
  the harness will "prove" the player correct against a reference carrying the same bug. It is 12
  because AKL encodes only envelope 8 or 0xa and EDGEA is 12 throughout. **A different tune needs a
  different value, or AKG, which carries the shape properly.**
- **The song is exported at the address it will be played from.** Both formats hold absolute
  pointers. Getting it wrong fails silently at run time; nothing asserts the address, only the size.
- **Paths nothing has ever called are not tested paths.** In the AKL player, arpeggio tables, pitch
  tables, soft-and-hard instruments and effects 0, 1, 2, 5 and 6 have never executed, because EDGEA
  uses none of them. They are written and they look right; that is not the same thing. Choosing a
  Targhan song for the demo is partly aimed at this — `export_akl.py --check` reports when a tune
  strays into one.
- **The offline chain is not a per-frame register mapping.** `ym2sn.py` does whole-song analysis —
  a priority bass channel, sub-122 Hz tones synthesised with periodic noise, the hardware envelope
  averaged per frame. A runtime converter reproduces neither. This library gives you the tune
  **re-voiced for the SN76489**, not the same tune smaller, and the README must say so.

## Prior art, to be honest about in the README

Arkos ships a 6502 AKY player already, for Apple II + Mockingboard, Oric, and Atari + SONari — all
machines with a genuine AY. There is no official 6502 player for AKL, AKM or AKG, and no AY→SN76489
layer anywhere. That gap is what this repo is.
