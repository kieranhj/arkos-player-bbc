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

## What the conversion gets wrong

Three things, all of them here rather than in a replay, so all of them affect
every player equally. **Two are now fixed**; each is marked. The measurements
below are what the problems looked like, and are worth keeping because they
are how the fixes were judged. [`fidelity-plan.md`](fidelity-plan.md) has the
options that were weighed and what it cost.

### 1. The bass falls off the bottom of the chip — FIXED

**This was the big one.** The
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

Fixed twice, and the host chooses with `bass_mode`. **Mode 1**, the
software bass voice: the channel's tone is parked at an inaudible 125 kHz
and a User VIA T1 timer bit-bangs the note in the volume domain, a real
square wave costing no musical channel. **Mode 2**, the periodic-noise
bass: `ym2sn`'s own trick, the noise generator with its feedback bit clear
clocked by tone generator 3, costing no timer and no interrupt but giving
the channel up whenever a drum wants it. One voice either way, sticky to
its channel. See below, and `fidelity-plan.md`.

### 2. Noise rate 3 — FIXED, and it was never a drum

This entry used to say that rate 3 is "the tuned noise", how you get a
*pitched drum*, and the largest remaining difference on percussion. **All
of that was wrong**, and it was wrong in `PLAN.md` and in Edge Grinder's
notes as well. Read `ym2sn.py`: a drum always gets `4 + rate` — the
feedback bit set, one of the three fixed rates (`ym2sn.py:1881`) — and rate
3 is emitted in exactly one place, `else: if bass_active` (`ym2sn.py:1886`).
Rate 3 is the **periodic-noise bass**, and nothing else. (Tuned *white*
noise, rate 7, exists behind `ENABLE_TUNED_NOISE`, which is off by default
and was never used.) The "1,701 frames" figure was wrong too: ym2sn only
writes the noise register when it changes, so 1,701 was the number of
*writes*. EDGEA has 9,990 frames of periodic bass.

So there was no percussion gap here. Rate 3 is `bass_mode 2` now — see the
bass section above and `fidelity-plan.md`.

There *was* a real percussion gap, and it was somewhere else: **the rate
table**. `ay_noise_rate` put its thresholds at AY periods 8 and 16 and
called that "nearest by period". Nearest by period is 12 and 24; nearest by
frequency, which is what ym2sn does, is 10.7 and 21.3. It was neither. Nine
entries changed, and on EDGEA that is 1,088 of 3,020 noise calls — 36%.
Across the 75-song corpus the median song changes on 1% of its noise calls
and 17 of the 75 on more than 20%. `tools/make_tables.py` derives it from
the two clock rates now.

### 3. The envelope was sampled, not averaged — FIXED

It drove a channel's volume on 33% of EDGEA, and **every envelope in that
tune runs 1.17 to 2.89 complete cycles per 50 Hz call** — so what the ear
gets is the mean of the ramp, while a single sample is whichever point it
landed on. That is why envelope frames agreed with the offline chain on 3.6%
of tone periods.

Fixed with a constant: a complete sweep of the AY's 5-bit ladder averages
0.1961 of full amplitude, which is level 12 and SN attenuation 7. `ay2sn`
emits it whenever the envelope completes at least one whole cycle in a call,
and keeps sampling when it is slower. About 15 cycles.

Note that the whole envelope model — the constant's threshold and the
`env_recip` table — assumes the player is called **50 times a second**. A
25 Hz host must double both.

## Choosing `bass_mode`, and wiring mode 1

The SN76489's lowest note is 122 Hz, and between a third and nearly half of
every tune measured goes below it. `bass_mode` picks what happens to those
notes:

| `bass_mode` | | interrupts | costs |
|--:|---|---|---|
| **0** | shift them up an octave | none | the tune's bass line |
| **1** | **software bass**: park the channel's tone at an inaudible 125 kHz and bit-bang the note in the volume domain from a VIA timer — a real square wave | a VIA timer, 102–157 IRQ/s | nothing musical |
| **2** | **periodic noise**: the SN's noise generator with the feedback bit clear is a 1/15 duty pulse train clocked by tone generator 3, so tone 3's period sets the pitch and the whole bass register is in reach. This is what `ym2sn.py` does | **none** | the drums, while it plays |

**Which voices exist at all is `BASS_MODE`, an assembly-time constant the
host defines** (decision 10): `-1` assembles all three and lets the host store
into `bass_mode` at run time, `0`, `1` or `2` assemble one and give the rest of
the bytes back - 589 of them for no bass, 217 for the periodic voice alone.
`docs/performance.md` has the table. Everything below is about which voice to
want.

Mode 2 needs nothing from the host but `BASS_MODE = 2`. It is the default on
all five demo discs, it is the one to reach for on a host that cannot spare a
timer or tolerate extra interrupts, and it is **the only bass path the
simulator can test**, py65 having no VIA.

Mode 1 is off until the host wires it up, because it needs an interrupt:

1. put **User VIA T1 in free-run** (ACR bit 6 set, bit 7 clear) so it reloads
   itself;
2. call `bass_irq` when User VIA T1 interrupts — and **test the flag against
   the enable**, `lda IFR : and IER : and #&40`. Masking a VIA interrupt does
   not stop its timer, so bit 6 goes on being set while T1 is disabled, and
   testing IFR alone services the bass on the back of every other interrupt in
   the machine. That mistake cost an afternoon: it made mute not mute and the
   bass crackle. The full account is in
   [`fidelity-plan.md`](fidelity-plan.md);
3. set `bass_mode` to 1.

Do not take the System VIA's T1: it is the MOS's own 100 Hz tick, and taking
it breaks the OS.

Which to choose is the drums against the interrupts. Mode 2 gives the voice up
whenever a drum wants the noise channel, which over the 75-song corpus is
**10% of the median song's bass calls** (mean 15%, seven songs above 40%);
mode 1 never does. Against that, mode 2 costs no timer at all, and per call it
is only 105–147 cycles dearer than mode 1 (EDGEA 2,389 against 2,494, Orion
Prime L4 2,307 against 2,454) — which is less than mode 1's interrupts cost on
top.

**There is one voice either way**, and it is sticky — the channel holding it
keeps it while it still wants it, because choosing the lowest-numbered
claimant each call made it hop 25 times a second on a tune where two channels
play the same low note. One voice covers 99.5% of Rhino's below-floor notes,
81.5% of EDGEA's and 78.7% of Dead On Time's, but over the corpus **30 songs
want three simultaneous bass voices and 26 want two**, so it is a real
limitation; the rest octave-shift as before.

`akl_silence` stops the bass as well as the four channels, so muting really
mutes. The bass is only as steady as the interrupt latency — measured at about
±1% within a note.

## Why this is not "the same tune, smaller"

An offline converter and a runtime one are not doing the same job.
`ym2sn.py`, which produced the pre-converted logs this was measured against,
does **whole-song analysis**: it picks a priority bass channel and synthesises
tones below the SN's floor using periodic noise, and it low-passes the
hardware envelope across each frame. `ay2sn.asm` sees one frame at a time.

That was the story, and the fidelity work has largely closed it.
`tools/compare_streams.py` decodes both streams to the chip's *state* at
the end of each frame and compares only what could be heard:

| | tone period | tone volume | noise byte | noise volume |
|---|--:|--:|--:|--:|
| Rhino, Acid Demo 21 (no envelope) | **100.0%** | **100.0%** | **100.0%** | 73.1% |
| EDGEA (32% envelope) | 97.8% | 97.4% | **100.0%** | 35.1% |

against 63.9% / ~25% and 3.6% / 5.9% before this work started. **On a tune
without a hardware envelope the runtime converter now reproduces the
offline chain exactly** - every tone period, every tone volume and every
noise byte, over all 9,600 calls of Rhino's Acid Demo. The periodic bass lands on
**99.9% of the frames ym2sn puts it on**, and never on one it does not —
6,165 of ym2sn's 6,173 on Rhino's tune, 13,600 of 13,608 on EDGEA — which
is a runtime picker with no lookahead agreeing with a whole-song analysis.

**Two things are left.** The tone-volume gap on EDGEA is the hardware
envelope and nothing else, which is E2/E3 in `fidelity-plan.md`. And **the
drums come out 2 to 3 SN steps - 4 to 6 dB - louder than ym2sn's**, because
ym2sn mixes the noise at a share of each open channel's *amplitude* and
`ay2sn` takes the loudest channel whole. That is the noise-volume column,
and it is the likeliest of the two to be heard.

The volume mapping itself used to be a third: `ym_sn_vol` was the
dB-faithful curve where ym2sn's default is a plain halving, and the 4-bit
to 5-bit widening differed by a step on every even volume. Both are ym2sn's
now (KC, 2026-09-05) and between them they are the whole of 23.5% to
100.0%.

So what this library gives you is close to what the offline chain gives
you, and no longer a different arrangement of it. Render both and listen:

```
python tools/verify/verify.py --player akl --snf build/runtime.snf
python tools/sn2wav.py build/runtime.snf -o runtime.wav
```

## The register file

`ay_regs` is 14 bytes in AY order, declared in `ay2sn.asm` because every
player fills it. R13 carries one convention of its own: **255 means "the
envelope shape was not re-sent this frame"**, which both players use and the
verification harness understands.
