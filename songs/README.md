# The songs

**These tunes are not covered by this repository's MIT licence.** Each is
used by permission of its composer. If you fork this repo, the code comes
with you and the music does not.

| file | composer | terms |
|---|---|---|
| `Acid_demo_21.aks` | Rhino (David Newman) | Distribution permitted by the author. Six channels — see below. **This is the AKY demo disc's tune.** |
| `Acid_demo_07.aks` | Rhino (David Newman) | An earlier iteration, three channels. Kept as the single-PSG case; its arrangement is not the same — it is missing the opening pattern. |

## The six-channel one

`Acid_demo_21.aks` carries two PSGs. Only the first three channels are music:
**the second three are event data riding on the Arkos command stream.**

`aky_init` reads the channel count out of the AKY header and steps the linker
by the whole entry, so it plays the first PSG and ignores the rest. No
preprocessing, no stripping, no separate export — it verifies against Arkos's
own player with no audible mismatch at all. See `docs/porting.md`.

The demo disc used `_07` while the player was still single-PSG only. That was
the wrong tune: it is an earlier arrangement and is missing the opening
pattern. `_21` is the one to use now that six channels play.

`lib/aklplayer.asm` cannot help you here, and neither can AT2's AKL exporter,
which squashes six channels into three without a word of warning — one reason
the AKL disc uses a different tune. See `docs/format-akl.md`.

## A hard test case

Rhino's tune leans on a **tuned bass**, and the SN76489's lowest note is 122
Hz. 43% of its audible channel-frames are below that floor and come out an
octave high — the worst of any tune measured. It is the right tune to judge
the conversion by, and the wrong one to conclude the players are broken from:
at the register level it is exact.

## What Arkos ships

Arkos Tracker bundles a couple of dozen of Targhan's own songs under
`songs/STarKos/` and `songs/ArkosTracker2/`, and uses two of them as its own
players' test music. `example/build.py` defaults the AKL disc to
`Targhan - Dead On Time - Ingame.sks` for that reason. They are not copied
into this repository — point `--song` at your Arkos install.
