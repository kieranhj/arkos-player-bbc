# The songs

**These tunes are not covered by this repository's MIT licence.** Each is
used by permission of its composer. If you fork this repo, the code comes
with you and the music does not.

| file | composer | terms |
|---|---|---|
| `Acid_demo_07.aks` | Rhino (David Newman) | Distribution permitted by the author, given to KC for the Nova invitro. Single PSG, so the players here can play it. |
| `Acid_demo_21.aks` | Rhino (David Newman) | The same tune, later iteration. **Two PSGs / six channels** — see below. |

## Two PSGs

`Acid_demo_21.aks` is a six-channel song: two AY chips. Every Arkos AKY
player, including this one, is single-PSG, and a BBC has one sound chip.
`tools/verify/verify.py` refuses it with an explanation rather than playing
half of it.

`Acid_demo_07` and `Acid_demo_08` are earlier, single-PSG iterations of the
same piece, which is why `_07` is the one on the AKY demo disc. To use `_21`,
open it in Arkos Tracker 3 and export a version with one PSG.

## What Arkos ships

Arkos Tracker bundles a couple of dozen of Targhan's own songs under
`songs/STarKos/` and `songs/ArkosTracker2/`, and uses two of them as its own
players' test music. `example/build.py` defaults the AKL disc to
`Targhan - Dead On Time - Ingame.sks` for that reason. They are not copied
into this repository — point `--song` at your Arkos install.
