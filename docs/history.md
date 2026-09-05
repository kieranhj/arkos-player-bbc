# How this library got built

`PLAN.md` is what is left. This is the record of what happened, kept because
the reasoning behind a finished step is worth more than the step.

Everything here is done. Where a step turned out differently from the plan,
the plan is quoted and then corrected — that difference is usually the useful
part.

---

## Why it exists at all

A tracker replay is a different trade from a register log. Edge Grinder's
349-second tune is 23,514 bytes as a `.vgi` and 4,741 as AKL tracker data,
because a register log stores the *output* and output grows with length while
a song mostly does not.

Nobody had done it on the BBC. Arkos ships 6502 players, but only for AKY and
only for machines with a real AY — Apple II with a Mockingboard, Oric, Atari
with a SONari. The BBC has an SN76489 and no AY at all, so every Arkos player
needs a conversion layer that existed nowhere.

Extracted from the Edge Grinder port (`BEEB/Repos/edge-beeb`, `MUSIC_AKL`),
where the AKL player was built, proved and parked. It follows
`vgm-player-bbc`'s shape — `lib/`, `docs/`, a demo, an MIT `LICENSE` — and is
named to match it.

## The licence question, settled before any code moved

- **Arkos Tracker 3 ships `LICENSE.txt`**: MIT, "Copyright (c) 2016-2025
  Julien Nevo". AT2 had no licence file; its terms were only on the website
  FAQ (*"Of course! The players are MIT-licensed... in any production, free or
  sold, open or closed source"*), archived as `LICENSES/arkos-faq-at2.md`.
- **The 6502 AKY ports carry their own MIT licences**: Apple II / Oric by
  Arnaud Cocquière, 2019; Atari 8-bit by Krzysztof Dudek (xxl), 2021.
- **The `SongTo*.exe` exporters are NOT covered** — that sentence says
  *players*. They are never redistributed; every tool takes the path to an
  Arkos install from config.
- Crediting Arkos is non-mandatory. This repo does it anyway, prominently.

---

## The steps, and what each one actually took

Each had an acceptance test. Nothing was believed without one.

### 1. Repo, licences, vendored reference

*Accepted when* every file in `reference/` and `lib/` had a row in
`PROVENANCE.md` naming its origin, its Arkos version and its licence.

The AT2 Lightweight sources were vendored **especially**: AT3 deleted them and
nowhere else keeps them. That instinct was right twice over — AT3 later turned
out to ship a V0 AKM player alongside a V1 exporter, so the vendored copy is
the only fixed point.

### 2. Lift AKL and `ay2sn` from edge-beeb

*Accepted when* `verify.py --player akl` printed `IDENTICAL on every frame`
and `{'ch2 period': 11}` over all 17,446 frames of EDGEA.

Those eleven are Arkos's own documented ±1 in the volume/pitch effects between
its PC side and its Z80 player, not a defect. `ENV_BASE` and the song address
became parameters of `aklplayer.h.asm` rather than constants buried in the
body.

### 3. `make_tables.py`

edge-beeb had committed `akl_ay2sn_tables.asm` with **no generator anywhere**,
so nobody could say where a number came from or change one.

*Accepted when* the generator reproduced edge-beeb's committed copy byte for
byte.

**It grew.** The plan named one missing generator; there turned out to be two
files and five tables, and recovering the envelope-step derivation
(5,120,000 / period, wrapped to 16 bits) took longer than anything else in the
step.

### 4. Port AKY

xxl's Atari version (658 lines, MADS) rather than the Apple/Oric one (1,306
lines, ACME): half the size, and its entire hardware coupling is two constants
and one register write, redirected into `ay_regs`.

*Accepted when* it matched `SongToYm.exe` on the same terms as AKL.

**It needed a header parser nobody planned for.** The AKY binary opens with a
header whose length depends on the PSG count, and the player wants the linker
that follows it. Getting that wrong does not fail — it plays silence,
convincingly. `aky_init` parses it rather than trusting a caller.

AKY does so little per frame that `ay2sn` becomes the dominant cost, which
makes it the stress test for the conversion layer.

### 5. The demo disc

A plain SSD: no ZX0, no loader, player in main RAM, its own VSync IRQ, and a
palette-write raster band so the cost is **visible**.

*Accepted when* it booted in jsbeeb and played, with the band matching the
simulated cost.

**The demo tunes changed.** The plan said one Targhan song; it became one per
player. Targhan's *Dead On Time* on the AKL disc, **Rhino's Acid Demo 21** on
the AKY disc — KC has the author's permission. `_21` is a two-PSG,
six-channel song, which is why the disc briefly used the single-PSG `_07`
instead; `aky_init` handles multiple PSGs now, and `_07` turned out to be a
different arrangement missing the opening pattern.

**The AKL disc could not have used Rhino's tune anyway**: AT2's exporter
produces unplayable AKL for it. That is why the discs do not share a song.

**The replay rate is not in the exported data.** A song that is not 50 Hz
plays at the wrong speed with nothing at all to show for it — *Dead On Time*
is 25 Hz and the first disc played it at exactly double speed, in tune, with
the right notes. Caught by ear. `tools/arkos.py` reads the rate out of a
`SongToYm` header, the only place it is written down.

**`ENV_BASE` was set for EDGEA and wrong for everything else.** The format's
own shapes are 8 and 10; 12 is an EDGEA-specific compensation. It is not
defaulted in the library at all now — a default is exactly how it came to be
wrong.

### 6. README and docs

The format table, the measured costs, the API, the credits, and the traps
stated loudly rather than buried.

### 7. The fidelity work

Noise rate 3 and the two bass voices are built; see
[`fidelity-plan.md`](fidelity-plan.md), which is still live. Rate 3 turned out
**not** to be "the tuned noise" or a percussion feature at all — in `ym2sn.py`
it is only ever the bass. The real percussion gap was the noise **rate table**,
which was nearest by neither period nor frequency.

The volume curve is `ym2sn`'s as of 2026-09-05, and with it the runtime
converter reproduces `ym2sn`'s whole-song offline output **exactly** on a tune
without envelopes: every tone period, tone volume and noise byte over all
9,600 calls of Rhino's Acid Demo.

### 8. AKM, added the same day

Not in the original plan — decision 5 said "noted now, ported later". It went
from nothing to a proved player and a disc in one day, and the route is
written up in [`porting.md`](porting.md) because it is the route to take for
AKG.

What made it fast was building the oracles first: a Python reference checked
against `SongToYm.exe`, and then a second oracle AKL never had —
`SongToAkm.exe` annotates every byte it exports, so
`tools/verify/akm_source_check.py` can hold the decode against Arkos's own
statement of it. The 6502 was identical to its reference on the first run.

Two findings came out of it that outlive the port: AKM derives its periods and
so disagrees with Arkos's own note table on six notes
([`format-akm.md`](format-akm.md)), and **Arkos Tracker 3 ships a V0 player
with a V1 exporter**.

---

## What was believed at the start and turned out wrong

- *"AKL is the cheapest player ever measured on this project, 2,183 cycles a
  frame."* That figure predates the fidelity work; the current AKL cost with
  the whole conversion is about 2,690.
- *"AKM has no 6502 player anywhere."* True when written, and the reason to
  port it. There is one now.
- *"AKM beats AKL."* Its data does, on every tune. Its player is 549 bytes
  bigger and it costs more per call, so on a short tune AKL still wins. See
  the README's tables.
