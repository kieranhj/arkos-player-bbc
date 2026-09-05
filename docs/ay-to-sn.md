# ay_regs to the SN76489

`lib/ay2sn.asm` is the only part of this library that knows what machine it
is on. It reads the fourteen AY-3-8912 registers a player left in `ay_regs`
and writes the BBC's SN76489 through the System VIA. About 1,100 cycles.

## The arithmetic that is exact

**Tone.** The CPC's AY runs at 1 MHz and the BBC's SN at 4 MHz, and the two
chips divide their clocks by 16 and 32 respectively. The whole conversion
therefore reduces to **SN period = 2 x AY period**, with periods over ten
bits halved an octave at a time until they fit. A shift and a clamp.

**Volume.** The AY's 5-bit envelope ladder steps -0.75 dB; the SN attenuates
in -2 dB steps. So attenuation = (31 - level) x 0.75 / 2, truncated —
truncating never makes a note quieter than the AY intended, where rounding
would. Level 0 is silence, which is attenuation 15 rather than 11.
`tools/make_tables.py` generates the 32-entry table from exactly that.

**Noise.** The noise byte is `&E4 | rate`, not `&E0 | rate`. **Bit 2 is the
feedback bit and it selects white noise.** With it clear the chip plays
*periodic* noise — a short repeating LFSR pattern, which is a pitched buzz,
not a drum, and every percussion hit comes out as a note. That was a real bug
in the Edge Grinder build, heard before it was found.

The drum's loudness is the volume of whichever AY channel has the noise open,
and that channel usually has its *tone* disabled — so the volume has to be
taken **before** the tone-disable test forces the channel to attenuation 15.
The loudest such channel wins.

## What is still missing

**Two of these are now fixed** - the envelope mean and the bass - and what
follows describes the problems as they were measured, with the fixes noted.
See [`fidelity-plan.md`](fidelity-plan.md).

Three things, all known, all affecting every player equally because they live
here rather than in a replay.

**The bass falls off the bottom of the chip, and this is the big one.** The
SN's period is ten bits, so its lowest note is 4 MHz / (32 x 1023) = **122
Hz**. `ay2sn` halves an AY period that will not fit, an octave at a time - so
every bass note below that comes out an octave high. `tools/verify/verify.py`
measures it per tune:

| tune | audible channel-frames below the floor |
|---|--:|
| Rhino - Acid Demo 07 | **43.0%** |
| Targhan - Dead On Time (Ingame) | 40.8% |
| EDGEA | 32.6% |

A third to nearly a half of every tune tried. A tune that leans on a tuned
bass - Rhino's does - will be the one that sounds most wrong. `ym2sn.py`'s
answer is to synthesise those notes with **periodic noise** on a priority
bass channel, which is the same mechanism as the tuned noise below; the two
fixes are really one piece of work.

The other two:

1. **Noise rate 3 — the tuned noise.** The SN's fourth noise rate clocks the
   noise generator from tone generator 3, which is how you get a *pitched*
   drum, and how a converter fakes a bass below the SN's 122 Hz floor.
   `ym2sn.py` uses it on 1,701 frames of Edge Grinder's tune. `ay2sn.asm`
   never emits it at all, only the three fixed rates. This is the largest
   remaining difference on percussion.

2. **The envelope is sampled once a frame, not averaged across it.** It
   drives a channel's volume on 33% of that tune, and every envelope in it
   runs at 1.2 to 2.9 complete cycles per 50 Hz field — so the per-frame
   level is an artefact of *how* you average, and a single sample is the
   crudest choice available. A closed-form average of a saw over a window is
   a few multiplies; budget a couple of hundred cycles.

Both are planned, with options and costs, in
[`fidelity-plan.md`](fidelity-plan.md).

## Why this is not "the same tune, smaller"

An offline converter and a runtime one are not doing the same job.
`ym2sn.py`, which produced the pre-converted logs this was measured against,
does **whole-song analysis**: it picks a priority bass channel and synthesises
tones below the SN's floor using periodic noise, and it low-passes the
hardware envelope across each frame. `ay2sn.asm` sees one frame at a time.

Compared frame for frame against a shipping VGM of the same tune:

| | tone period exact | volume exact |
|---|--:|--:|
| non-envelope frames | 63.9% | ~25% |
| envelope frames (33% of the tune) | 3.6% | 5.9% |

That is not arithmetic error. On a channel where every AY register is
constant, the offline stream sweeps 440 to 554 to 659 to 880 Hz —
information that is simply not in the frame.

So what this library gives you is **the tune re-voiced for the SN76489**, not
the same tune in less memory. Render both and listen:

```
python tools/verify/verify.py --player akl --snf build/runtime.snf
python tools/sn2wav.py build/runtime.snf -o runtime.wav
```

## The register file

`ay_regs` is 14 bytes in AY order, declared in `ay2sn.asm` because every
player fills it. R13 carries one convention of its own: **255 means "the
envelope shape was not re-sent this frame"**, which both players use and the
verification harness understands.
