# Improving the fidelity: the envelope and the bass

**E1 and B2a are BUILT, 2026-09-05.** Both are in `lib/ay2sn.asm` and both
run on the demo discs. What was found doing it is at the bottom, under
"What the implementation turned up". E2/E3 and B1/B2b/B2c remain options.

**Planned 2026-09-05.** Everything below lives in
`lib/ay2sn.asm`, so it benefits every player in the library at once. The
replays themselves are already exact against Arkos's own output; what is
wrong is the conversion to a chip the music was not written for.

All figures are measured — from the YM register logs of three tunes, from
the SN76489 and VIA pages of the BBC wiki, and from `ym2sn.py` and
`vgcplayer_bass.asm`. Cycle counts marked *(est)* are hand-counted from the
instruction sequences, not simulated; `tools/verify/verify.py` will give the
real ones once there is code to run.

---

## 1. The envelope

### What is wrong

`ay2sn` samples the hardware envelope **once per player call**. The envelope
runs far faster than that, so a single sample is an arbitrary point on a ramp
that has already been round several times.

Measured over EDGEA's 5,730 envelope frames (33% of the tune):

| | |
|---|--:|
| envelope cycles per player call | min **1.17**, median 1.86, max **2.89** |
| calls completing at least one whole cycle | **100.0%** |

That last figure is the whole story. **Every single envelope frame in that
tune completes at least one full cycle**, so the ear hears the *mean* of the
ramp, while we emit a value that swings across the full 0–15 attenuation
range depending on where the sample happened to land. It is why envelope
frames agree with the offline chain on only 3.6% of tone periods.

Averaging must happen in the **linear amplitude** domain, not on the
attenuation index — attenuation is logarithmic, and averaging logarithms is
not the average of the sound. `ym2sn.py` says the same thing and keeps a pair
of tables for it.

### The constant

A complete sweep of the AY's 5-bit ladder (−0.75 dB a step) averages
**0.1961 of full amplitude**, which on the SN's 2 dB ladder is **attenuation
7**. One number.

### Options

| | what it does | cost *(est)* | covers |
|---|---|--:|---|
| **E1** | If the envelope completes ≥1 cycle this call, emit the constant (attenuation 7). Otherwise keep sampling. | **~15 cycles** | 100% of EDGEA's envelope frames |
| **E2** | E1, plus a weighted correction for the leftover partial cycle: `avg = (n·mean + partial_area) / (n + frac)` | ~200 cycles | exact, any rate |
| **E3** | Sample the ramp at 4 points across the call, average in the linear domain through a LUT and convert back | ~120 cycles | generic, also right when the envelope is slow |

**Recommendation: E1 now, E3 if a tune needs it.** E1 is close to free and
fixes the entire measured problem; the branch it needs (is the step ≥ a whole
cycle?) is one comparison on the existing `env_step`, which is already the
per-call phase increment. E2's extra precision is worth little when the
partial cycle carries 15–45% of the window and the rest is a constant.

The risk is a tune with a *slow* envelope, where cycles-per-call is well
under 1 and the constant would be badly wrong. E1 keeps the sampling path for
exactly that case, and E3 is the upgrade if such a tune turns up. Note that
neither of the two other tunes tested uses the hardware envelope at all, so
this is one tune's evidence.

---

## 2. The bass

### What is wrong

The SN's tone period is ten bits, so its lowest note is
4 MHz / (32 × 1023) = **122.2 Hz**. `ay2sn` halves any period that will not
fit, an octave at a time, so every bass note below that comes out an octave
high.

Measured, per tune, over audible channel-frames:

**Across all 72 songs Arkos ships** (`tools/survey_tunes.py`, which writes
`build/tunes.md` and commits nothing): 29 want three simultaneous bass
voices, 25 want two and 17 want one. So one voice is a real limitation on
most tunes, and B2b is worth more than the first three tunes suggested.
Those 72 also include four 25 Hz songs and **one at 100 Hz**, and the
heaviest envelope use is 100% of frames against EDGEA's 33%.

| tune | below the floor | simultaneous bass voices needed |
|---|--:|---|
| Rhino – Acid Demo 07 | 43.0% | **never more than one** (always ch0) |
| Targhan – Dead On Time | 40.8% | 1 for 83% of frames, 2 for the rest |
| EDGEA | 32.6% | 1 for 91%, 2 for 99.5%, 3 for 0.5% |

Bass frequencies run **29–122 Hz**, median 44–69 Hz depending on the tune.

**One bass voice fixes most of the problem and all of Rhino's.**

### Option B1 — periodic noise (what `ym2sn.py` does)

Set the noise register to `&E3`: feedback bit clear (periodic) and rate 3,
which clocks the noise from tone generator 2. Tone 2's period register then
sets the pitch, and the note comes out at `8333 / period` Hz — a range of
8.1 Hz to 7.8 kHz, so the whole bass register and more.

`ym2sn` picks one **priority bass channel** per song (the one with the most
low notes) and routes its low tones this way.

- **Runtime cost: ~60 cycles a call** *(est)* — a comparison per channel, then
  the noise byte, tone 2's period and one volume. No interrupts.
- **Timbre**: the wiki is explicit that SN "periodic noise" is *not* noise —
  the LFSR is reset to a single set bit which circulates, giving a **1/15
  duty-cycle pulse train**. That is a thin, reedy bass, not a square wave.
- **What it costs you: two of the four channels.** The noise channel carries
  the bass, so **the drums stop**; and tone 2's period is the clock, so tone
  2's own note is lost. On Rhino's tune the bass sounds on 61% of frames, so
  the percussion would be gone for most of the tune.

### Option B2 — software bass, bit-banged (what `vgcplayer_bass.asm` does)

Set the channel's tone period to **1** — a 125 kHz carrier, inaudible, and
the analog chain's ~8 kHz low-pass removes it anyway — and then **toggle that
channel's attenuation between the note's volume and silence** from a VIA
timer running at the note's half-period. The square wave is generated in the
volume domain.

Simon's player runs three of these at once, one per tone channel, on User VIA
T1, User VIA T2 and System VIA T2, with a self-modifying `BEQ`/`BNE` (`EOR
#$20`) flipping the handler between "write volume" and "write silence".

- **Runtime cost**: two interrupts per cycle per sounding note. Measured
  rates: **102–157 IRQ/s** per voice across the three tunes, worst case 244
  at the top of the range. At ~65 cycles an interrupt *(est, including
  dispatch)* that is **0.5–0.8% of the CPU** for one voice — about 200–350
  cycles a frame, against a 79,872-cycle frame budget.
- **Timbre**: a true square wave at the note's own volume.
- **What it costs you: nothing musical.** The bass stays on its own tone
  channel; the drums and the other two tones are untouched. This is the
  decisive advantage over B1.
- **What it costs you: a timer, and steady interrupts.** The wiki's VIA page:
  four timers exist, System VIA T1 is usually MOS sound, leaving System VIA
  T2 and both User VIA timers. **T1 has a free-run mode that reloads itself**,
  so a T1 voice needs no reload in the handler; T2 is one-shot only and the
  handler must rewrite `T2C-H` every time — which is exactly what Simon's
  System VIA T2 handler does.
- **The real risk is jitter.** The square wave is only as steady as the
  interrupt latency. A host that disables interrupts for long stretches, or
  runs a heavy raster-timed handler, will modulate the bass pitch audibly.
  Edge Grinder is exactly that kind of host: it owns IRQ1V and System VIA T1
  for the two-cycle rupture, so a bass voice there would have to be a User
  VIA timer and would still be at the mercy of the rupture's timing.

### Options, side by side

| | channels lost | timbre | cost *(est)* | interrupts |
|---|---|---|--:|---|
| **B0** current: shift up an octave | none | wrong pitch | 0 | none |
| **B1** periodic noise | noise + tone 2 | 1/15 pulse train | ~60 cyc/call | none |
| **B2a** software bass, 1 voice, User VIA T1 free-run | none | square wave | ~200–350 cyc/frame | 102–157/s |
| **B2b** software bass, 2 voices (+ User VIA T2) | none | square wave | ~2× the above | ~300/s |
| **B2c** software bass, 3 voices (+ System VIA T2) | none | square wave | ~3× | ~450/s |

**Recommendation: B2a.** One software bass voice on User VIA T1 in free-run
mode. It is the cheapest of the software options — free-run reloads itself —
it costs no musical channel, it fixes 100% of Rhino's bass and ~90% of the
others, and it is a true square wave rather than a pulse train. Add B2b only
if the two-voice frames turn out to matter by ear.

Keep B1 in mind for one specific case: a host that cannot tolerate extra
interrupts at all. It is the only zero-interrupt option that gets the pitch
right.

---

## Order of work

1. ~~**E1**, the envelope constant.~~ **Done.**
2. ~~**B2a**, one software bass voice.~~ **Done**, and working on both demo
   discs - but see the open question below before trusting it.
3. Re-measure and **listen**: `verify.py --snf` then `tools/sn2wav.py`,
   against Arkos's own `SongToWav.exe` render of the same tune. **Not done.**
4. Only then consider B2b and E3.

## What the implementation turned up

**The bass costs a little more than estimated.** Both changes together add
about 106 cycles to the mean 50 Hz call (2,164 to 2,270 on EDGEA) - the
envelope test and the per-channel floor check, which run whether or not a
voice is claimed.

**Do not inline the sound-chip write in the interrupt.** The first version
of `bass_irq` had its own copy of `sn_write`'s sequence, shortened: it held
the write strobe low for 6 cycles where `sn_write` holds it for 10, and
wrote all eight bits of the System VIA's port B rather than read-modify-
writing the low four. The interrupt ran - the phase byte toggled - and **not
one write reached the chip**. Calling `sn_write` (and saving X around it)
fixed it immediately. `sn_write` is the sequence that is known to work; use
it and pay the ten cycles.

**An open question about the edge timing.** Captured out of jsbeeb, the bass
edges come at the right average rate - mean 21,601 cycles against an
expected 22,912, within 6% - but one edge lands at *exactly* 446 cycles into
every frame, immediately after the music's last write, while the others
drift freely as they should.

That 446 is suspiciously exact. Real interrupt latency varies by a few
cycles; a fixed offset every single frame looks like the sound write being
**queued behind the music's ten writes** and timestamped when the chip takes
it, rather than the interrupt being late. Rewriting the timer latches only
when the note changes (which is now what happens, and is right anyway) did
not shift it, which argues against the timer's phase being pulled.

**It is not settled**, and the way to settle it is to time `bass_irq` itself
- a breakpoint or a counter - rather than reading the timing off the sound
capture, which is downstream of whatever the chip model does. Until then,
treat the bass as working and its jitter as unmeasured.

**One voice has to be shared, and naively it thrashes.** The first version
claimed the voice for the lowest-numbered channel below the floor. On
Targhan's Dead On Time that channel changes on **17.7% of bass calls with a
median run of ONE call** - both channel 0 and channel 2 play the same low
note - so the voice hopped 25 times a second and was retuned each time.
`bass_pick` is sticky now: the channel that had the voice keeps it while it
still wants it. Rhino's tune never changes channel and EDGEA changes on 2.4%,
so neither showed the problem.

**The one that caused the crackle: test a VIA flag against its ENABLE.**
Masking a VIA interrupt does not stop its timer. T1 goes on free-running and
goes on setting IFR bit 6 while it is disabled, so a handler that tests
`IFR & &40` alone will service the bass **on the back of every other
interrupt in the machine**. That one mistake caused three separate symptoms:

  * mute did not silence the bass - the four volume-off writes went out and
    the interrupt wrote the channel straight back up again;
  * a bass edge appeared at *exactly* the same offset into every frame,
    immediately after the music, which is what the "+446" note below was
    describing;
  * and the edges were irregular, which is audible as a crackle.

`lda IFR : and IER : and #&40` is the idiom, and it is what
`vgcplayer_bass.asm` does - `and $fe6e` - which I had read and not copied.
With it, the pinned edge is gone (offsets now spread across the frame) and
the jitter within a note falls from about ±3.5% to under **±1%**.

**And a click on every bass note ending.** `bass_update`'s stop path wrote
the channel's volume as well as stopping the timer - and wrote it as
attenuation 0, full blast, for one call. It was not only wrong but
unnecessary: bass_update runs at the END of a call, after the volume writes,
and on a call where nobody claimed the voice the music has already written
that channel's real volume.

**`bass_stop` is unconditional.** It used to skip the hardware when
`bass_running` said the timer was already off, and the flag and the chip got
out of step.

**The pitch is right and the jitter is small.** Measured on a single note,
with the timer value read at the same moment: mean 8,576 cycles an edge
against 8,576 expected - **100.0%**, 116.6 Hz intended and 116.6 Hz
delivered - with individual edges spread about ±3.5%. That supersedes the
"one edge pinned at +446" worry above, which came from measuring across note
changes and comparing against a timer value read at a different moment.

**The simulator cannot test any of this.** `verify.py` runs in py65 with no
VIA, so `bass_enable` stays 0 there and its floor metric still reports the
octave shift. That figure is now measuring the *fallback* path. Only jsbeeb
sees the bass.

## How this gets verified

**The existing harness cannot see any of it**, and that needs saying. It
compares `ay_regs` frame for frame against Arkos's own player, and none of
this work changes `ay_regs` — it all happens below that line, in `ay2sn` and
in the interrupt. The AY-level checks stay green whatever we do here, which
is exactly why they stayed green while the bass was an octave out.

So the checks for this work are different ones:

- **`verify.py`'s floor metric** — the "shifted up an octave" percentage
  should fall to zero for the channel carrying the bass. That is already
  implemented and is the direct measure of B2.
- **A new envelope metric** — the same idea for the envelope: compare the
  emitted attenuation against the linear-domain average of the true ramp,
  and report the error distribution.
- **`tools/sn2wav.py` against `SongToWav.exe`** — render both and compare by
  ear, and by the melody-tracking measure already used once (percentage of
  50 ms windows within half a semitone).
- **jsbeeb, for B2** — the software bass is interrupt-driven, so it has to be
  measured on a running machine, not in py65. Capture the SN write stream and
  check the toggle intervals are the intended half-periods and that they do
  not drift.
