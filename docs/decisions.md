# Decisions

KC's, binding, in the order they were taken. A deviation from any of these is
agreed **before** it is built and recorded here after.

| # | date | decision |
|--:|---|---|
| 1 | 2026-09-05 | **Scope**: replay + AY→SN, BBC-framed — but every player stays strictly hardware-free behind the `ay_regs` boundary, so a replay alone travels to an Oric or an Apple II. |
| 2 | 2026-09-05 | **Demo tune**: an Arkos-bundled Targhan song, not EDGEA. EDGEA is third-party and exercises the least of any player. |
| 3 | 2026-09-05 | **Timing**: extract now; finish the fidelity work here rather than in edge-beeb. |
| 4 | 2026-09-05 | **edge-beeb's copy** becomes a verbatim copy in its `lib/`, the same treatment as `lib/vgiplayer.asm`. This library is upstream; edge-beeb never edits it. **Done 2026-09-06**: five files copied byte for byte, its `lib/README.md` says so, and its `-Akl` build takes `ENV_BASE = 12` and `BASS_MODE = 2` (its decision 70). The copies' own `INCLUDE "lib/..."` lines are written relative to a repo root, which is what lets a copy be verbatim rather than a fork - keep that. |
| 5 | 2026-09-05 | **AKM**: noted now, ported later. Superseded the same day — it was ported, and steps 1–3 of `porting.md` are complete. |
| 6 | 2026-09-05 | **Edge Grinder** stays on VGI. `MUSIC_AKL` remains the parked comparison build. Fidelity work here can feed back if and when KC's ear says so. |
| 7 | 2026-09-05 | **The AKM period table is BUILT, not lifted.** AKM derives its periods at run time by halving twelve octave-0 entries, and that disagrees with Arkos's own 128-note table on six notes — so `lib/akl_periods.asm` cannot be shared. `make_tables.py` generates `lib/akm_periods.asm` from AKM's own arithmetic, so the table is provably the loop it replaces. 256 entries, because the note index is 8-bit and wraps. |
| 8 | 2026-09-05 | **The AKM mixer is assembled AKL's way** — one byte with per-channel masks, bits 0–5 — rather than the Z80's rotate-through-three-channels, which leaves bits 6–7 as whatever fell out. Identical in every audible bit, and it keeps the two players reading the same way. |
| 9 | 2026-09-05 | **`ENV_BASE` is never defaulted**, for any player. It is a property of the song, and a default is exactly how it came to be wrong for every tune but one. `tools/arkos.py`'s `envelope_base()` works it out and serves AKL and AKM alike. |
| 10 | 2026-09-06 | **`BASS_MODE` is an assembly-time constant, host-defined and never defaulted** - the same treatment as `ENV_BASE`, and for a related reason: BeebASM cannot ask whether a symbol exists, so a default would be a choice the host did not make. `-1` keeps every bass path and lets the host store into `bass_mode` at run time, which is byte-identical to the build before this existed and is what `example/demo.asm` uses, because its B key compares the three by ear. `0`, `1` or `2` assemble one voice and give the rest of the bytes back: **-589 bytes for no bass at all**, -259 for the software voice alone, -217 for the periodic one. The cycles are the small half (9 a call for the dispatch itself), except for a host that wants NO bass, which paid 120 cycles a call for the option. See `docs/performance.md`. |

## Standing rules that are not numbered decisions

- **Nothing is believed without an acceptance test**, and every figure in
  these documents says what it was measured on and when.
- **Say which oracle a number came from.** AT2's `SongToYm.exe` and AT3's
  disagree — the same EDGEA comparison gives 11 audible mismatches against one
  and 431 against the other, with the 6502 byte-identical to its reference in
  both runs. See [`verification.md`](verification.md).
- **A path nothing has ever called is not a tested path.** Five of AKL's seven
  effects have still never executed. `tools/survey_akm.py` exists so that AKM
  can at least say which of its paths its testing reached. The same applies one
  level up, to *tunes*: WON4 had never been played, and had been wrong all
  along - see [`format-akl.md`](format-akl.md).
- **Do not redistribute the Arkos exporters.** The MIT sentence covers the
  *players*.
