# Taking this somewhere else

## To another 6502 with a real AY

`lib/aklplayer.asm` and `lib/akyplayer.asm` contain no BBC-specific code.
They fill `ay_regs` and stop. To drive a real AY instead of the SN76489,
replace `lib/ay2sn.asm` with fourteen register writes and keep everything
else — the players do not change at all.

`akyplayer.asm` is a port of a player that did exactly that, so if you are on
an Apple II, an Oric or an Atari you should use Arkos's own version rather
than this one: `reference/PlayerAky_atari_mads.asm` and
`reference/PlayerAKY_apple_oric_acme.a`. They are faster, being able to write
the chip directly.

## The one change worth understanding

The Atari AKY player writes each register as it computes it:

```
lda #reg   : sta AYR
lda value  : sta AYD
```

Here every such pair became `sta ay_sel` / `jsr ay_put`, and `ay_put` is the
whole hardware layer:

```
.ay_put
{
    stx ay_xtmp
    ldx ay_sel
    sta ay_regs,x
    ldx ay_xtmp
    rts
}
```

That is about 19 cycles a write against the Atari's 8, on a dozen or so
writes a frame. It buys a **mechanically faithful** port: the decode is byte
for byte the Atari's, which is what lets it be checked against Arkos's own
player output. Folding the register number into a direct store per site would
save a few hundred cycles a frame — do it if you need them, and re-run
`tools/verify/verify.py` afterwards.

## To AKM - DONE

`lib/akmplayer.asm` exists and is the only 6502 AKM player there is. What
follows is the route it took, kept because it is the route to take for AKG.

**The one thing worth doing differently next time**: `SongToAkm.exe` without
`-bin` annotates every byte it exports, and `tools/verify/akm_source_check.py`
turns that into a second oracle - one that shows a decode fault on the cell
that caused it, rather than waiting for a register log to show it hundreds of
frames later. Build that FIRST, not last. AKL has no equivalent and would be
easier to finish if it did.

AKM needed two things AKL did not: **its own period table** (AKM halves twelve
octave-0 entries at run time and that disagrees with Arkos's own 128-note
table on six notes, so `lib/akl_periods.asm` cannot be shared), and **256
entries in it**, because AKM's note index is 8-bit and wraps where AKL's is
masked to seven bits.

The original note, kept for AKG: 3,654 bytes against AKL's 4,741 for the same
tune, upstream-supported, and **no 6502 player existed anywhere**. Arkos's Z80
player and format documentation are in an Arkos Tracker 3 install
(`players/playerAkm/`), and `reference/AKM.md` is the spec.

Take the same route this project took for AKL, in this order, because it is
the order that catches mistakes early:

1. Transcribe the Z80 into Python first and check it against
   `SongToYm.exe`'s register log for the same song. Debugging a format
   misunderstanding in 6502 is much harder than in Python.
2. Write the 6502 against that reference, frame for frame.
3. Only then put it on a disc.

`tools/verify/verify.py` already has the shape for a third player: add the
export, add the entry point, and the harness does the rest.

Note that AKM shares AKL's envelope limitation — only shapes 8 and 0xa — so
whatever `ENV_BASE` does for AKL, an AKM player will need too.

**AKG would not need it at all**: it carries the true envelope shape. See the
next section.

## To AKG - the one format still without a player

**AKG is now the only Arkos format with no 6502 player anywhere.** Measured
2026-09-06 against an Arkos Tracker 3.7 install; every figure below says where
it came from.

### There is a Z80 player, and an annotating exporter

Both, current, and MIT:

| | AKG | AKM, for scale |
|---|--:|--:|
| `players/playerAkg/sources/z80/PlayerAkg.asm` | 168,061 bytes | 99,136 |
| the format spec (vendored as `reference/AKG.md`) | 741 lines | 336 |
| licence | MIT, Julien Névo | the same |

The Z80 player targets CPC, MSX, Spectrum, Pentagon, PCW and SVI, and has the
full Player Configuration system - conditional assembly that strips features a
given song does not use. There is nothing equivalent here and it is worth
knowing about before deciding how big an AKG player has to be.

**The second oracle is already available.** `tools/SongToAkg.exe` annotates its
source export the way `SongToAkm.exe` does: 1,750 of the 3,564 lines exported
for `songs/Acid_demo_07.aks` carry a comment, with Disark region markers.
`tools/arkos.py` already runs it - `envelope_base()` reads the true envelope
shapes out of it. So the thing this document says to build FIRST is a matter of
pointing `akm_source_check.py`'s approach at a different format, not of
inventing an oracle.

### What it would buy: the measured case

`tools/survey_envelopes.py` reads the shapes each song really uses out of that
export and sorts the corpus. As of 2026-09-06:

```
75 songs:  17 no hardware envelope
           50 fit one AKL/AKM (base, base + 2) pair
            8 fit NO pair          <- only AKG can carry these
shapes used, in songs: 8:42  9:1  10:31  12:12  13:1  14:3
```

The eight are *DemoIzArt - End Part*, *Orion Prime - Fight*, *Star Sabre -
Boss Theme*, *Hocus Pocus*, *Aganamemnon (soft drums)*, and Totta's *Hardy*,
*Rezzy* and *Crawlers* - the last two using shapes 13 and 9, the one-shot
envelopes that have no pair at all. **A further 15 songs need an `ENV_BASE`
other than 8**, which no export carries and which a host has to be told; AKG
removes the constant entirely.

Beyond the envelope, AKG has everything `reference/AKM.md`'s own limitations
list says AKM has not: several PSGs per subsong, events, hard-to-soft sounds,
unrestricted SoftAndHard, speed changes anywhere rather than only at the start
of a pattern, full arpeggio and pitch ranges, and the complete effect set.

**It might also be faster.** Targhan's AKM player header says AKM is *"much
slower than the generic one or the AKY player"*. `performance.md` bounds what
that is worth here: on *Crtc*, AKM's replay is 1,291 cycles of a 2,981-cycle
call and `ay2sn` plus the bass is the other 1,690, so even an AKG replay as
cheap as AKL's 920-963 saves **about 330-370 cycles a call, 12%**. The spine is
the majority of the frame whatever the format.

**It would cost RAM.** AKG's tune data is 10-36% bigger than AKM's and 2-5%
bigger than AKL's on the five tunes in `performance.md`, and its player would be
bigger again - the Z80 source is 1.7x AKM's. AKG is the fidelity and coverage
choice, not the size choice, and "AKM for a long tune, AKL for a short one"
does not change.

### The catch, and it is the important part

**`lib/ay2sn.asm` never reads `ay_regs+13`.** The envelope block models exactly
one shape - `env_shape` in `lib/ay2sn_tables.asm` is a linear 0 to 31 ramp -
and in the fast case it emits `ENV_MEAN_LEVEL` and does not sample at all,
which is the E1 decision in `fidelity-plan.md` and was measured to take EDGEA's
volumes to 97.4% of `ym2sn.py`'s.

So on the BBC, AKG's true shapes buy **nothing** until the spine learns real
shapes. That is an E2/E3-class change affecting all three existing players and
it needs its own measurement against `ym2sn.py`; it is not part of writing a
decoder. The envelope benefit is immediate only for a port to a machine with a
real AY, where `ay_regs+13` goes to the chip and does the work.

### The route, and what it should cost

The route is the AKM one above, in the same order, and the reason to expect it
to go the same way is that all three things that made AKM fast are present: a
Z80 reference to transcribe, an annotating exporter for the cell-by-cell
oracle, and a harness that already has the shape for another player. AKM went
from nothing to a proved player and a disc in one day (`history.md`).

Against that, AKG's spec is 2.2x the size and its instrument cells are
genuinely richer - SoftToHard, HardToSoft and a full SoftAndHard, each with
optional hardware arpeggio, hardware pitch and forced periods. Call it a few
days for a verified player.

The open-ended part is not AKG at all. It is whether `ay2sn` should grow real
envelope shapes, because without that the headline benefit stays on paper.

## Multiple PSGs

A six-channel Arkos song carries two PSGs, and a BBC has one sound chip.
`aky_init` handles it: a linker entry is a duration word and then one track
pointer per channel, so it reads the first three pointers and steps by the
whole entry. **The first PSG plays and the rest is ignored**, at a cost of
one byte of state and no preprocessing.

That is not just a fallback. Arkos songs sometimes carry non-musical data on
a second PSG - Rhino's Acid Demo puts *event data* on channels 4 to 6, riding
on the command stream - and in that case playing the first PSG alone is
exactly right rather than a compromise.

`lib/aklplayer.asm` has no equivalent: AKL is a single-PSG format and its
exporter squashes a six-channel song into three without a word (see
`format-akl.md`).

## The AKY header

The AKY binary does not start with the linker, and the player wants the
linker. The header is one flags byte, one channel-count byte, then a
four-byte PSG frequency **per PSG** — so six bytes for a three-channel song
and ten for a six-channel one. Arkos's own testers dodge this by using the
source export and its labels; a binary export has to compute it, so
`aky_init` parses the header itself rather than trusting a caller.

Getting it wrong does not fail. The player reads the PSG frequency as a
linker entry and plays convincing nonsense — silent channels, period 1 —
which is exactly what it did here first time, with the host computing the
offset. That is why the player does it now.
