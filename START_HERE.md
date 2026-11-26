# arkos-player-bbc: start here

Arkos Tracker music on the BBC Micro: AKL, AKM and AKY 6502 replays plus the AY-3-8912 to SN76489 conversion layer. A library (used by edge-beeb's Edge Grinder port) with three demo discs.

| | |
|---|---|
| GitHub | https://github.com/kieranhj/arkos-player-bbc (public) |
| Upstream | Arkos Tracker's own Z80 players (the reference the 6502 replays were transcribed and verified against) |
| Local path | D:\beeb\mine\arkos-player-bbc (moved from OneDrive\BEEB\Repos\arkos-player-bbc in the 2026-11 tidy) |
| Branch | master (only branch) |
| Last commit | 2026-11-21: Add Arkos Tracker songs: Roguecraft-Next and h0ffman tunes |

## What's in here
- `lib\`: the players (`aklplayer.asm`, `akmplayer.asm`, `akyplayer.asm`, each with a `.h.asm`) and the AY->SN layer (`ay2sn.asm`, `ay2sn_tables.asm`); edge-beeb takes `lib\` verbatim.
- `example\`: `demo.asm` and `build.py`, the demo-disc build.
- `tools\`: exporters (`export_akl.py`, `export_akm.py`), `make_tables.py`, `compare_formats.py`, `sn2wav.py`, surveys; `tools\verify\`: the verification suite.
- `songs\`: test songs (not MIT, see README "Credit"). `reference\`: Arkos reference material. `docs\`: history.md, decisions.md, fidelity-plan.md.
- CLAUDE.md, PLAN.md, README.md.

## Build and run
- `make`: `py -3 example\build.py` -> `build\ARKOS-AKL.SSD`, `-AKY.SSD`, `-AKM.SSD` (Makefile added 2026-11-22). Works.
- `make extra` (ARKOS-EDGEA / ARKOS-ORION discs), `make verify` (verify.py --player akl, make_tables.py --check), `make help`.
- Tools: beebasm (`bin\beebasm.exe` if present, else `..\..\Bin\beebasm.exe`), Python 3 with py65 and numpy, Arkos Tracker 3 at `ARKOS3_HOME` (default `D:\tools\trackers\ArkosTracker3`, which stays in OneDrive) for song export and the oracle.
- Run the `.SSD` in any BBC emulator (no run script here).

## Local changes
- Working tree clean apart from the new Makefile and this file. No snapshot branches.

## Status and next steps
- PLAN.md: all three players verified and all three demo discs boot (2026-09-05). Next is listening: compare each player with Arkos's own SongToWav render (PLAN.md section 1), then the rest of PLAN.md.
- Recent: songs added 2026-11-21; warning for mid-pattern speed changes (2026-09-11).

## See also
- README.md (API, which format to pick), CLAUDE.md (build/verify commands, rules), PLAN.md, docs\decisions.md.
- D:\beeb\mine\edge-beeb (uses `lib\`).
