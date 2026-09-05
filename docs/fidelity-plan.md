# Improving the fidelity: the envelope and the bass

**E1 and B2a are BUILT, 2026-09-05.** Both are in `lib/ay2sn.asm` and both
run on the demo discs. What was found doing it is under "What the
implementation turned up". E2/E3 and B1/B2b/B2c remain options, and
**section 3 is new**: KC has allowed light preprocessing of a song at export,
which changes how the bass channel should be chosen.

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

**Across a 75-song corpus** — everything an Arkos install ships, plus this
repo's own songs and EDGEA (`tools/survey_tunes.py`, which writes
`build/tunes.md` and commits nothing) — **30 want three simultaneous bass
voices, 26 want two and 18 want one**. So one voice is a real limitation on
three quarters of them, and B2b/B2c are worth more than the first three
tunes suggested. The corpus also holds four 25 Hz songs and **one at
100 Hz**, and the heaviest envelope use is 100% of calls against EDGEA's
32%.

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

| | channels lost | timbre | cost | interrupts |
|---|---|---|--:|---|
| **B0** `bass_mode 0`: shift up an octave | none | wrong pitch | 0 | none |
| **B1** `bass_mode 2`: periodic noise | the drums, while it plays | 1/15 pulse train | +309 cyc/call | **none** |
| **B2a** `bass_mode 1`: software bass, 1 voice, User VIA T1 free-run | none | square wave | +200 cyc/call, and 200-350 a frame in the handler | 102-157/s |
| **B2b** software bass, 2 voices (+ User VIA T2) | none | square wave | ~2x the above | ~300/s |
| **B2c** software bass, 3 voices (+ System VIA T2) | none | square wave | ~3x | ~450/s |

Measured on Dead On Time, per 50 Hz call: mode 0 2,370 cycles, mode 1
2,570, mode 2 2,679. Most of the +200 mode 1 and mode 2 share is
`bass_pick`'s scan, which mode 0 skips entirely.

**Both B1 and B2a are built now**, and the host chooses with `bass_mode`.
The original recommendation, and the reasoning still stands as the default:
**B2a**, one software voice on User VIA T1 in free-run mode. It costs no
musical channel, it is a true square wave rather than a pulse train, and it
never has to give the voice up to a drum.

**B1 is the answer for a host that cannot afford the interrupts** - which,
KC, is most of them, and is why it was built rather than kept in mind. It is
the only zero-interrupt option that gets the pitch right, it needs no timer
and no wiring, and it is the only bass path `verify.py` can test in py65,
since the simulator has no VIA. What it gives up is the drums while it
plays: 10% of the median corpus song's bass calls, and 65% of the worst.

Neither is a second voice. That is still B2b, or B1 *beside* B2a - the
permutation and the sticky picker are already the pieces that would need,
and 95-100% of the frames wanting two voices have the noise channel idle.
Not built; KC parked the combination for later.

---

## 3. Preprocessing the tune (KC, 2026-09-05)

**Light preprocessing of a song is allowed.** The player does not have to
take any AK-anything file and work everything out at run time; it is fine to decide
things offline, at export, the way `ym2sn.py` does. That permission changes
what the bass can be.

### What the runtime picker costs, and why it exists

`bass_pick` scans the three channels **every call** and hands the one voice
to a claimant, preferring whoever had it last. It exists only because the
player is choosing with no lookahead: pick the lowest-numbered claimant and
the voice thrashes — on Dead On Time the lowest one below the floor changes
on 17.7% of bass calls, median run one call. The stickiness is a patch over
a decision that should never have been made at run time.

It costs about 80 cycles a call, one byte of state, and a rule someone has
to understand.

### What a priority channel would buy

`ym2sn` picks **one priority bass channel per song**, the one with the most
low notes, and routes only that channel's low tones. Done at export, the
whole of `bass_pick` disappears: no scan, no stickiness, no thrash, and the
choice can be made on the music rather than on channel numbers.

How well one fixed channel does, measured over the frames where any channel
is below the floor:

| tune | bass frames | best fixed channel covers |
|---|--:|--:|
| Rhino – Acid Demo 21 | 4,623 | **ch0, 99%** |
| Targhan – Dead On Time | 2,353 | **ch0, 91%** |
| EDGEA | 10,618 | ch0, **52%** (ch1 50%) |
| Targhan – Orion Prime L4 | 22,709 | ch2, **60%** (ch1 59%, ch0 58%) |

**So it depends entirely on the tune.** Where one instrument owns the bass a
fixed channel is as good as anything. Where the bass line moves between
channels — EDGEA and Orion Prime both spread it across all three — a fixed
channel abandons nearly half of it to the octave shift, which is *worse* than
the sticky runtime picker, because that at least follows the note wherever it
goes.

### The options

| | what is decided offline | data | runtime |
|---|---|---|---|
| **P1** | one priority channel for the whole song | 1 byte | none — delete `bass_pick` |
| **P2** | the priority channel **per pattern**, from the linker's own pattern list | ~1 byte a pattern | a lookup when the pattern changes |
| **P3** | per note: mark every note that should be software bass | a bitmap, or a parallel list | a test per note |

**A constraint the reference implementations do not have**: `ym2sn` owns its
output format, so it flags a software-bass note *inside* the stream — divide
the period by four, store it in ten bits, set bit 6 of the high byte, and
`vgcplayer_bass.asm` decodes it. We cannot. We replay **Arkos's** formats,
byte for byte, against Arkos's own player as the oracle; annotating the
stream would fork the format and cost us the thing that makes this library
trustworthy. So anything decided offline has to arrive as a **side-car** —
a small blob beside the song, not inside it.

That is cheap for P1 (one byte) and P2 (one byte a pattern, and the linker
already tells the player when a pattern starts). P3's side-car is the
expensive one, because "per note" in a tracker format means per cell of every
track, and the player would have to count cells to index it.

### Recommendation

**P2, and keep a runtime fallback.** One byte per pattern is nothing, the
pattern boundary is already a place where the player does work, and it tracks
a bass line that moves — which is the case a fixed channel handles worst and
which two of our four tunes are. Where a song really does keep its bass on
one channel, P2 degenerates to P1 for free.

Keep `bass_pick` as what happens when there is no side-car, so the library
still plays a bare `.akl` or `.aky` sensibly; it is the difference between a
library and a tool for one pipeline.

**This does not remove the need for more voices.** 56 of the 75 songs
surveyed want two or three simultaneous bass voices, and no amount of
choosing better fixes a frame that genuinely has two low notes in it. P2 and
B2b are independent, and B2b is the bigger win on that evidence.

## Order of work

1. ~~**E1**, the envelope constant.~~ **Done.**
2. ~~**B2a**, one software bass voice.~~ **Done**, and working on both demo
   discs.
3. ~~**B1**, the periodic-noise bass, and the noise rate table.~~ **Done**,
   and on the demo discs as `bass_mode 2`.
4. **The volume curve** - the open question below, and the biggest number
   left by a long way.
5. Re-measure and **listen**: `verify.py --snf` then `tools/sn2wav.py`,
   against Arkos's own `SongToWav.exe` render of the same tune. **Not done.**
6. Only then consider B2b (a second bass voice), P2 (choosing the bass
   channel offline, per pattern) and E3.

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
    immediately after the music - the "+446" pinning, which was first
    blamed on the emulator's sound-write queue and was nothing of the kind;
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
delivered. With the flag-versus-enable fault fixed, the spread within a note
is under **±1%**.

Two wrong diagnoses were made on the way here, both from the same mistake -
comparing a timing capture against a `bass_n` read at a different moment,
after the note had changed. One claimed the bass was an octave high; the
other blamed the "+446" pinning on the emulator's sound-write queue. Neither
was true: the pitch was always right, and the pinning was the IER fault
above. **Read the state and the timing at the same instant, on one note.**

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


---

## What B1 turned out to be

**Three things in the notes were wrong, and each was wrong everywhere.**

**Rate 3 is not a drum.** `PLAN.md`, `ay-to-sn.md`, this file and Edge
Grinder's `layer-7-music-arkos.md` all called it "the tuned noise", the way
to get a *pitched drum*, and "the largest remaining difference on
percussion". Read `ym2sn.py`: a drum always gets `4 + rate`, feedback set,
one of the three fixed rates (`ym2sn.py:1881`), and rate 3 appears in one
place only, `else: if bass_active` (`ym2sn.py:1886`). Rate 3 **is** the
periodic-noise bass. Tuned *white* noise is rate 7 and lives behind
`ENABLE_TUNED_NOISE`, which is off by default.

**"1,701 frames" was writes, not frames.** ym2sn only writes the noise
register when it changes - writing it resets the LFSR - so 1,701 was the
number of `&E3` writes. EDGEA has **9,990** frames of periodic bass, and
`ay2sn` now claims the voice on exactly 9,990 of them: a runtime picker with
no lookahead landing on the same frame set as a whole-song analysis.

**B1 does not cost tone 2.** ym2sn permutes which AY channel goes to which
SN tone slot (`ym2sn.py:1727-1770`), so the slot spent as the clock is the
bass channel's own, and its note is on the noise channel. Nothing musical is
lost - only the drums, and only while the bass plays. `ay2sn` keeps a
three-byte `sn_slot` map and swaps two entries; the parking code indexes the
latch tables through it, twelve cycles a call.

**There WAS a percussion gap, and it was the rate table.** `ay_noise_rate`
had its thresholds at AY periods 8 and 16, described as "nearest by period",
and was neither that (12 and 24) nor nearest by frequency (10.7 and 21.3).
Nine entries changed. On EDGEA that is 1,088 of 3,020 noise calls, 36%;
across the corpus the median song changes on 1% and 17 of 75 on more than
20%. Fixed first, on its own commit, and derived from the clock rates now.

**The divide by 15 is closed-form, not a loop.** The SN's periodic noise
runs at a fifteenth of tone generator 3, so the period is
`round(2 * ay_period / 15)` - exactly `ym2sn`'s `int(round())`. The first
version looped `x -> (x & 15) + (x >> 4)` and cost 468 cycles, because a
16-bit `lsr`/`ror` on absolute memory is 12 cycles a bit. Since
`256 = 15 * 17 + 1`, `x/15 = 17h + (h + l)/15` for `x = 256h + l`, and the
same identity reduces `h + l` to one byte whose remainder feeds back just
once. Two adds, a nibble swap and two compares, about 210 cycles, and proved
equal to `x // 15` on every value in the range.

**Rounding, not truncating.** At the bottom of the range one step of the
period is 25 cents. `round` halves the worst error to 11.8 cents, which is
the chip's own quantisation and no more, and it is what ym2sn does.

### How it was proved

The AY-level harness cannot see any of this - it compares `ay_regs`, and
this all happens below that line. So `verify.py` gained `--bass`, and
because **mode 2 needs no VIA it runs in py65 exactly as it runs on the
machine**, which the software voice never could. Over every frame of every
tune tried it reports: the emitted tone-3 period equals ym2sn's
`round(2p/15)` on every claimed call, the noise byte is `&E3` on every one,
the clocking slot is silent on every one, and there are **zero** redundant
noise writes (each would reset the LFSR and click).

Then in jsbeeb: twelve consecutive fields of SN writes captured off the
running AKY demo in NOISE mode occur in the simulated stream and nowhere
else - the same proof the AKL player itself got. And the mode switch was
watched in memory: `bass_running` goes 1 to 0 when the host moves from mode
1 to mode 2, so the software voice's timer really is shut down.

Coverage, as a share of the channel-frames below the chip's floor:

| tune | rescued by one periodic voice |
|---|--:|
| Rhino, Acid Demo 21 | **99.5%** (4,612 of 4,635) |
| EDGEA | 81.5% (9,990 of 12,255) |
| Targhan, Dead On Time | 78.7% (2,353 of 2,989) |

The remainder is frames wanting two voices at once, not frames B1 got wrong.

---

## The volume curve - OPEN, and the biggest number left

`tools/compare_streams.py` holds the runtime stream against ym2sn's offline
one, decoded to the chip's *state* at the end of each frame. With B1 on:

| | tone period | volume | noise byte |
|---|--:|--:|--:|
| Rhino, Acid Demo 21 (no envelope) | **100.0%** | 23.5% | **100.0%** |
| EDGEA (32% envelope) | 97.8% | 28.7% | **100.0%** |

Periods and noise are done. **The volume column is one table and one line
of code**, and it is not the envelope - Rhino's tune has no envelope at all.

Two differences, both against `ym2sn`'s *default* settings:

1. **`ym_sn_vol`.** Ours is `trunc((31 - level) * 0.75 / 2)`, the
   dB-faithful mapping: the AY's ladder is -0.75 dB a step and the SN's is
   -2 dB, so the AY's 23 dB of range lands in SN attenuations **0-11**.
   ym2sn's default is `15 - ((v + 1) >> 1)`, a plain halving, which spreads
   the same 23 dB over the SN's full **0-14**. Ours is the more faithful
   arithmetic; ym2sn's is louder at the top and genuinely quiet at the
   bottom, and it is what every stream anyone has listened to was made
   with. Ours is what ym2sn calls `-t`, and marks *Experimental*.

2. **The 4-bit to 5-bit widening.** Ours is `(v << 1) | 1`; ym2sn's is
   `(v << 1) | (v & 1)` (`ym2sn.py:1312-1318`), duplicating the low bit.
   They differ on every even volume, by one step.

**Measured**: making both changes takes Rhino's tune to **100.0% period,
100.0% volume, 100.0% noise** - the runtime converter reproducing a
whole-song offline analysis exactly - and EDGEA to 97.8% / 97.4% / 100.0%,
the residual being the envelope, which is E2/E3's problem and nobody else's.

It is not built, because it changes the volume of every note in every build,
including Edge Grinder's `-Akl`, and that is KC's call and not a defect to
be quietly fixed. Change 2 alone is a bug-shaped thing; change 1 alone gets
Rhino to 54.9%. Both together are the 100%.