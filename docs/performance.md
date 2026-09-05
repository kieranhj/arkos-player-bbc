# Performance — where the cycles go, and what can be had back

Measured 2026-09-06, `tools/profile_player.py`, py65 at 2 MHz, `bass_mode 2`.
Every figure here says what it was measured on. Nothing is estimated unless the
row says **estimate**, and no estimate is presented as a measurement.

The tool this rests on is new: `tools/profile_player.py` runs the real `lib/`
sources — the same image `verify.py` verifies — and attributes every executed
cycle to the routine that spent it, using beebasm's own `-dd` label dump so
that the locals inside a `{}` block are visible. Before it, every optimisation
argument this repo had was made from reading the source.

```
python tools/profile_player.py --player akm --song "X.aks" --frames 800
```

---

## 1. The finding that governs everything else

**`ay2sn` and the bass are 56–69% of a call, and they are shared by all three
players.** The replay everyone argues about — AKL against AKM against AKY — is
the minority of the cost.

| player | tune | ay2sn + bass | the replay |
|---|---|--:|--:|
| AKY | Rhino, Acid Demo 21 | 1,483 (**69%**) | 678 (31%) |
| AKL | Tom&Jerry, Edge Grinder | 1,519 (**62%**) | 920 (38%) |
| AKL | Targhan, Orion Prime L4 | 1,652 (**63%**) | 963 (37%) |
| AKM | Targhan, Crtc | 1,690 (**57%**) | 1,291 (43%) |

A cycle saved in `lib/ay2sn.asm` is saved three times. A cycle saved in a
replay is saved once, on the tunes that use that format. That is the whole
ranking, and it is why everything built below is in the spine.

### Inside the spine, per call (AKL, EDGEA, 700 frames)

| block | cycles | what it is |
|---|--:|---|
| `sn_write` | 320 | ten bytes out to the chip, 32 cycles each plus the `jsr` |
| `ay2sn.nonzero` | 232 | packing each channel's three SN bytes |
| `ay2sn.tone_on` | 113 | the period: AY × 2, split into lo/hi |
| `ay2sn.fit`/`.fits` | 92 | halving until it fits ten bits |
| write tail (`no_v0..2`) | 94 | the nine unconditional tone/volume writes |
| `ay2sn.have_vol5` | 63 | volume LUT, and the noise-open test |
| `ay2sn.got_step` | 62 | the envelope phase accumulator and its shape lookup |
| `bass_pick` | 146 | which channel may take the one bass voice |
| `div15` | 86 | the periodic bass's period, when it is claimed |
| `ay2sn.slot_id` | 43 | resetting a three-entry table with a loop |

### The single biggest redundancy

`ay2sn` wrote **ten bytes to the SN76489 on every call, unconditionally**. The
chip's tone and volume registers latch, so writing a byte the register already
holds is audibly nothing and costs 38 cycles.

| tune | player | SN bytes a call | already in the chip |
|---|---|--:|--:|
| Targhan, Orion Prime L4 | AKL | 10.00 | **95%** |
| Rhino, Acid Demo 21 | AKY | 10.06 | **90%** |
| Tom&Jerry, Edge Grinder | AKL | 10.00 | **87%** |
| Targhan, Crtc | AKM | 10.21 | **62%** |

After the cache, the same measurement reads **0.60 to 1.54 bytes a call, of
which 0% say anything the chip already holds**. The layer now sends what
changed and nothing else.

---

## 2. What was built, and what it cost

Five changes, all in `lib/ay2sn.asm`, all **chip-state identical**: the SN's
eight registers hold the same values at the end of every frame as they did
before. The byte stream is deliberately *not* identical — eliding bytes is the
whole point — so the acceptance test reconstructs the chip's state from the
stream and compares that instead. It is
[`tools/verify/chip_state.py`](../tools/verify/chip_state.py), and it is new.

```
python tools/verify/chip_state.py --corpus
  … 39 songs …
  39 identical, 0 differ, over 900 frames each.
  mean 2631 -> 2414 cycles a call (-8.2%)
```

1. **A write-through cache.** Ten bytes of state (`sn_cache_*`), and a byte is
   only sent when the register does not already hold it. A tone write is a
   latch/data *pair* and is elided as a pair. The noise control register is
   never deduped this way — writing it resets the LFSR, which is a click, and
   it has its own `noise_last` dedupe for exactly that reason.
2. **`sn_write` stopped setting DDRA per byte.** It is set once a call
   instead. This also freed X and Y, which is what made (1) affordable — see
   the host requirement in §5.
3. **The envelope block tested the same thing twice.** Whether the envelope
   completes whole cycles inside one call decides both the phase step and
   which level goes out; it was worked out once, then worked out again forty
   cycles later by re-reading the same two registers. Now once. In the fast
   case the shift, the table lookup and the second test all go, and the phase
   still advances — so a later slow envelope resumes from the right place.
4. **The noise channel's volume joined the cache.** It was the one byte still
   going out on every single call: the drum path, the silent path and the
   periodic bass all wrote it unconditionally. Caught by capturing the *real*
   write stream out of jsbeeb, not in the simulator.
5. **Three micro-fixes**: the three-entry slot table is written as three
   constants rather than a loop (−17 a call); the halving loop no longer
   tests the same byte twice and `jmp`s back (−3 an iteration); one of the
   two nibble shifts that pack the second tone byte became a four-entry
   lookup (−4 a channel, for four bytes).

### Full-tune cost, before and after

`tools/verify/verify.py`, whole tune, cycles per 50 Hz call. The "before"
column reproduces the README's committed figures exactly, which is the check
that the two harnesses agree.

| player | tune | mean before | mean after | | max before | max after |
|---|---|--:|--:|--:|--:|--:|
| AKL | Edge Grinder | 2,693 | **2,494** | −7.4% | 3,873 | 3,900 |
| AKL | Orion Prime L4 | 2,712 | **2,454** | −9.5% | 3,889 | 3,871 |
| AKL | Dead On Time | 2,683 | **2,541** | −5.3% | 3,686 | 3,594 |
| AKM | Crtc | 2,954 | **2,805** | −5.0% | 5,004 | 5,032 |
| AKM | Edge Grinder | 2,746 | **2,546** | −7.3% | 4,463 | 4,489 |
| AKM | Dead On Time | 2,775 | **2,634** | −5.1% | 4,267 | 4,229 |
| AKY | Acid Demo 21 | 2,228 | **2,050** | −8.0% | 2,739 | 2,714 |
| AKY | Dead On Time | 2,343 | **2,195** | −6.3% | 2,771 | 2,779 |

**The worst frame is flat** — +28 at worst, −92 at best, and better on four of
the eight. That was the thing to watch, and the reason the mean is the smaller
claim of the two: a cache pays a comparison on every byte and only sometimes
saves a write, so the frame where every register changes gets dearer, not
cheaper. It does, by under 30 cycles. On a raster-timed host the max column is
the one that decides, and it did not move.

Cost: **+73 bytes** in total — the player-plus-converter image goes from
3,612 bytes to 3,685 — of which 10 bytes are the cache itself. Against a
library whose whole case is total RAM, 73 bytes for 5–10% of the frame is the
trade this section is really reporting.

---

## 3. What is available and not built

Ranked by cycles per unit of risk. None of these is started.

| # | where | worth | risk | what |
|---|---|--:|---|---|
| D | AKL, AKM | ~70–90 **(estimate)** | low | The players build the register file in `chan_per_lo/hi`, `chan_vol`, `noise_reg`, `reg11/12`, then copy thirteen bytes into `ay_regs` — 104 cycles of pure copying. Writing straight into `ay_regs` removes most of it. `chan_vol,x` → `ay_regs+8,x` is free; the periods need `ldy per_idx,x` and cost 4 a site to save 8. |
| E | `bass_pick` | ~100 **(estimate)** | medium | `bass_pick` scans all three channels reading R7 twice, the volume and the period — and then the channel loop reads all of it again. The two passes exist because the voice must be granted *before* any channel claims it. Merging needs the loop split, or the scan's results kept in a mask. |
| F | `div15` | ~80 on hit **(estimate)** | low | 86–152 cycles a call, and the bass note usually does not change between calls. A two-byte input compare (~10 cycles) would skip it on a sustained note. Pure RAM-for-cycles: 4 bytes. |
| G | all three | 155–216 **(measured ceiling)** | high | Zero page. See below — the ceiling is real but unreachable in full. |
| H | AKY | ~70 **(estimate)** | low | `ay_put` costs 33 cycles a register write including the caller's `sta ay_sel`. `sty tmp : ldy aky_amp,x : sta ay_regs,y : ldy tmp` is 15. The player's own header already says to do this "if it ever matters". |

### On inlining, and on the branches and jumps

Two of the questions that started this have short measured answers.

**Call overhead.** A `jsr` is 6 cycles and its `rts` 6, so every subroutine
in a frame costs 12 before it does anything. Measured, after the work above:

| | AKM/Crtc | AKL/EDGEA | AKY/Acid |
|---|--:|--:|--:|
| `jsr`/`rts` pairs a call | 20.9 | 19.4 | 12.5 |
| cycles, before any of them works | **251** | **233** | **150** |
| share of the call | 9.1% | 10.5% | 8.3% |

That is the *ceiling*, and a ceiling only: inlining a routine called from
three sites costs three copies of its body, and this is a library whose case
is total RAM. `sn_write` was the one worth attacking, and the cache attacked
it from the other end — the cheapest call is the one that never happens.

**Needless branches and jumps.** Three were found and all three are fixed:
`jmp got_step` in the envelope block became a fallthrough; `jmp fit` closed
the halving loop by jumping back to re-test a byte it had just tested, and
is now a `bcs` to the shift itself; and the three-way `bass_skip` test in the
write tail (`beq no_v0` / `cmp #1 : beq no_v1` / `cmp #2 : beq no_v2`) became
one `cpx bass_skip` inside `sn_chan`. What is left in `ay2sn` is a
`jmp ch_loop` that cannot be a branch — the loop body is about 176 bytes and
a relative branch reaches 128 — and the `jmp bass_update`s that close the
three tails, which are real tail calls rather than waste.

**Constants.** Nothing worth factoring: the repeated `#15`, `#&f0` and
`#ENV_MEAN_LEVEL` are immediates and already cost nothing to name. The one
repeated *value* is `ay_regs+7`, the mixer, read twice per channel and once
more in `bass_pick` — six absolute loads a call, 24 cycles. It could live in
zero page, and that is item G below rather than a separate idea.

### On zero page, measured rather than assumed

`tools/profile_player.py` now counts executed instructions by addressing mode
and reports what the zero-page form would save. The answer is not uniform, and
one half of the folklore is wrong here:

| | AKM/Crtc | AKL/EDGEA | AKY/Acid |
|---|--:|--:|--:|
| `sta abs` + `lda abs` and friends | 173 | 148 | 143 |
| `sta abs,x` → `sta zp,x` | 33 | 18 | 12 |
| `lda abs,x` / `abs,y` → zero page | **0** | **0** | **0** |
| ceiling if *everything* were zero page | **216** | **168** | **155** |

`lda abs,x` and `lda zp,x` both cost 4. The only difference is the
page-crossing penalty — and **the profiler measured 0.00 crossings a call on
all three players**, because the three-byte per-channel arrays happen not to
straddle a page. So the two hundred-odd `lda abs,x` a call are already as
cheap as zero page, and moving them would buy nothing.

What is left is the plain-absolute traffic and the indexed *stores*. AKL keeps
30 three-byte arrays; AKM keeps 41. Nobody can ask a host for 90–123 bytes of
zero page on top of the 22–25 the players already take. The realistic move is
a handful of the hottest arrays, and the honest figure for that is a fraction
of the ceiling above — which is why this is ranked last despite the biggest
headline number.

---

## 4. Tried, measured, and not taken

**Skipping the envelope generator entirely when no channel has bit 4 set.**
Sixteen cycles to test, ninety to skip; it looked free and it is not. On 37 of
the 39 corpus songs the chip state is identical. On two — *Tom&Jerry, From
Scratch Part 1* and *UltraSyd, Fractal* — it is not, because the envelope
phase stops advancing while the envelope is unused and a later **slow**
envelope then resumes from the wrong place. It is worth 2–72 cycles depending
on the tune, and it buys them with a fidelity change nobody has listened to.

Rejected as built. If it is ever wanted, it belongs in `fidelity-plan.md` with
a measurement against `ym2sn.py`, not in a performance patch.

**A 256-entry table for `snper >> 4`.** Built, measured, thrown away. It
turned four shifts into a lookup and saved 4 cycles a channel — 12 a call —
and cost 256 bytes plus up to 255 more of `ALIGN &100` padding to keep the
lookup off a page boundary. The whole optimisation was +569 bytes with it and
+73 without, for 12 cycles. Small is what AKL is for; the four-entry table
for the other nibble stayed, because four bytes is not a trade.

---

## 5. One new requirement on the host

`sn_write` no longer sets the System VIA's DDRA. `ay2sn`, `bass_irq` and
`akl_silence` each set it once on entry, and every byte in the burst that
follows relies on it still being set.

**So `ay2sn` must not be interrupted by anything that changes DDRA** — which
on a stock machine means the MOS's own 100 Hz keyboard scan. Call the player
from an interrupt handler (where the I flag is already set), or with `sei`
around it. `example/demo.asm` calls it from its `IRQ1V` handler and is
therefore already correct; this is written up in the README's API section.

The alternative is to put the two instructions back in `sn_write` and pay 2
cycles a byte and the loss of X — about 60 cycles a call, and the cache gets
dearer too because it has to save and restore the channel index around every
write. Measured at the time: the conservative form saved 139 cycles on EDGEA
where this one saves 181.

Verified on jsbeeb, Model B, `ARKOS-AKM.SSD`: the demo boots, plays, and its
captured SN write stream is the sparse one the simulator predicts.

---

## 6. How to reproduce any of this

```
python tools/profile_player.py --player akl --song "…/EDGEA.SKS" --frames 700
python tools/verify/verify.py --player akl --song "…/EDGEA.SKS" --bass 2
python tools/verify/akm_verify_corpus.py
```

The chip-state acceptance test — the one that says a byte stream may change
but the chip's registers may not — lives in `tools/verify/chip_state.py`.
