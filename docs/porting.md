# Taking this somewhere else

## What Arkos's own site says, checked 2026-09-06

<https://www.julien-nevo.com/arkostracker/index.php/players-overview/> and its
availability page, read 2026-09-06. It agrees with everything below, with one
wording trap.

- **6502 means AKY, and only AKY.** The availability page lists 6502 players
  for the Apple II, the Oric (Arnaud Cocquiere) and the Atari 8-bit with the
  SONari extension (Krzysztof Dudek). AKM and AKG appear under Z80 hosts only
  (CPC, MSX, Spectrum, PCW), AKY additionally under 68000 (Atari ST, ggn) and
  the Vectrex (Malban). So `lib/akmplayer.asm` is still the only 6502 AKM
  player, and AKG still has none anywhere.
- **Lightweight is not in the AT3 line-up at all.** Its one mention is under
  VG5000: a legacy player that existed in AT2, awaiting community interest for
  an AT3 adaptation. That is the same withdrawal `format-akl.md` describes, and
  the reason `reference/` keeps AT2's sources.
- **The AKM limitations list matches `reference/AKM.md` item for item**: one
  PSG per subsong, no hard-to-soft, restricted SoftAndHard, no events, no
  legato, no retriggering, speed changes only at the start of a pattern,
  arpeggio and pitch -64 to 63, expressions capped at 127, automatic period in
  software-mode instruments. The AKG section below argues from that list.
- **AKM being slower is upstream's own claim**, not just Targhan's player
  header: the AKM page says "slower performance compared to other AT3 players".

**The trap.** The overview sells AKM as memory-optimised with "significantly
reduced player and song file sizes" - both halves. Here only the song half
holds: `format-akm.md` measures the AKM player plus `ay2sn` at 4,161 bytes
against AKL's 3,612, most of the difference being AKM's derived period
table. There is no contradiction, because upstream is comparing a Z80 AKM
against AKG and AKY while this project compares a 6502 AKM against a format
AT3 no longer ships.
But **do not carry "AKM is smaller" over from the site as a statement about the
player**; the measured claim is "smaller data, bigger player, dearer call", and
that is the one that decides AKM against AKL here.

Note also that the site's own selection guidance - games: AKG or AKM;
size-limited: AKM; demos: FAP (CPC only) or AKY - has no opinion on the choice
this library actually offers, because AKL is not in it.

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

## To FAP - feasible, measured, and not worth doing

Investigated 2026-09-06 against Arkos Tracker 3.7. Every figure below was
measured that day; the exports are reproducible with

```
"$ARKOS3_HOME/tools/SongToFap.exe" <song> build/fap/<name>.fap
```

which prints the crunched size of each register stream, the decrunch buffer
size and the CPC play time. `compare_formats.py` does not know about FAP, so
these numbers are not in the generated tables.

### FAP is not a tracker format

It is a **compressed register log**, so it belongs beside VGC and VGI in
`performance.md` and not beside AKL, AKM and AKY. Twelve independent
per-register LZSS streams are decrunched a fixed budget at a time into a ring
buffer of one 256-byte page per register, and the play routine reads one byte
per register out of that buffer.

The compression is a 256-byte window LZSS with one-byte offsets, and the whole
of it is `thirdParty/fap/Lzss.cpp` lines 39-57 in the AT3 source tree:

| marker byte | meaning |
|---|---|
| `00`-`1E` | literal run of marker + 1 bytes, following inline |
| `1F` | end of this register's flow: loop |
| `20`-`FF` | match of marker - `1D` bytes, then one offset byte = distance - 1 |

Registers 1+3 and 5+13 are packed as nibble pairs, and three "this register
did not change" flags ride in bits 5-7 of the r6 stream. `FapCrunch.cpp`
writes the file: a skip-R12 flag, the max registers to play, fourteen initial
register values, twelve stream offsets, then the streams each followed by a
loop marker and a loop offset.

**There is no format document.** `players/playerFap/` has no `doc/` folder,
unlike `playerAkg/` and `playerAkm/`. Those 486 lines of C++ are the spec, and
they are MIT like the rest of AT3; the Z80 player is MIT too (Hicks & Gozeur,
2025).

### The measurement

Five tunes, exported 2026-09-06. The decrunch buffer is **2,882 bytes on every
one of them** - 11 streams of 256 plus 6 state bytes each, R12 being constant
in all five.

| tune | FAP data | AKM total | AKL total | AKY total | VGC total |
|---|--:|--:|--:|--:|--:|
| Rhino, Acid Demo 21 | 5,600 | 11,326 | - | 14,463 | 10,276 |
| Targhan, Dead On Time | 3,240 | 5,975 | **5,673** | 8,436 | 8,766 |
| Tom&Jerry, Edge Grinder | 12,358 | **7,888** | 8,426 | 16,682 | 17,518 |
| Targhan, Orion Prime L4 | 7,092 | **5,989** | 6,005 | 8,491 | 8,657 |
| Targhan, Crtc | 16,022 | **10,393** | - | 20,724 | 23,853 |

Upstream's compression claim holds: **FAP's data beats AKY on four of the five
and VGC on four of the five**, losing both times on Orion Prime alone.

Then add the fixed cost. `lib/ay2sn.asm` at `BASS_MODE = 2` measures **1,560
bytes**, the buffer is 2,882, and a decoder would be 500-800, so the fixed
overhead is about **5,150 bytes** against AKL's 3,685 and AKM's 4,234. That
makes the totals 8,390 for Dead On Time, 10,750 for Acid Demo 21, 12,242 for
Orion Prime, 17,508 for Edge Grinder and 21,172 for Crtc: **last or second to
last on every tune**, and Edge Grinder's 12,358 bytes of data do not fit the
demo's `&3000`-`&6000` at all.

### Why FAP's data beats VGC's, which is not the reason it looks

FAP and VGC are both per-register stream compressors, so the difference had to
be in the input or in the coder. `tools/stream_cost.py` measures the input
half: it reads the `.ym` `SongToFap` crunches and the `.vgm` `vgmpacker`
crunches - the same tune, after `ym2sn.py` has done the AY to SN conversion
offline - and puts one common coder over both. zlib -9 is the yardstick, with a
32K window, so it is not a size an 8-bit decoder can reach; what matters is the
ratio between the two columns.

| tune | AY streams | SN streams | the conversion costs |
|---|--:|--:|--:|
| Rhino, Acid Demo 21 | 2,832 | 5,248 | 1.85x |
| Targhan, Dead On Time | 2,212 | 4,181 | 1.89x |
| Targhan, Orion Prime L4 | 3,285 | 5,788 | 1.76x |
| Tom&Jerry, Edge Grinder | 5,958 | 12,298 | 2.06x |

**The SN76489 log of a tune is about twice as compressible-expensive as the AY
log of the same tune, before any compressor is chosen.** The per-stream rows on
Acid Demo say where it goes:

- **The period split.** The AY's 12 bits split 8+4, so the coarse byte is
  nearly static: r3 changes on 3.3% of frames, 3 distinct values, 54 bytes. The
  SN's 10 bits split 4+6, so both bytes are active: channel 0's low nibble
  changes on 40.1% of frames and costs 720, its high six bits on 43.8% and 834.
  An 8+4 split concentrates the churn in one stream; a 4+6 split spreads it
  over two.
- **The volumes.** r8 changes on 43.3% of frames and costs 267; SN vol0 changes
  on 19.3% and costs 445. Fewer changes, less *regular* changes - envelope
  simulation and requantising 16 AY levels onto a 4-bit log scale break up the
  patterns the AY log repeats.
- Each side gets a freebie. FAP drops r12 as constant and merges r5+r13 into
  118 bytes for two registers; VGC never carries the AY mixer at all, which is
  r7, 642 bytes here and FAP's single dearest stream at 1,317.

**The coder pulls the other way.** VGC's chain - 4-bit-run RLE, then LZ4 with a
255-byte window, then Huffman - lands within 1.2-1.4x of the zlib yardstick.
FAP's plain LZSS, with no entropy coding at all, lands within 2.0-2.2x. So FAP
starts with data that is 1.85x cheaper and hands about 1.4x of it back.

That is also exactly why **Orion Prime is the one tune FAP loses**: 24,192
frames of long, quiet streams is where Huffman amortises its tables, and there
the coder gap beats the content gap. Nowhere else does it. Against VGI, whose
coder is FAP's own kind, the content gap is all there is and FAP's data wins on
every tune - though `.vgi` v3 has since taken most of that back, and it did so
using this measurement. See below.

One thing not to misread in `vgmpacker`'s report: its `overhead=2040` is
decoder RAM, 8 windows of 255 bytes, not file bytes. It is the bulk of VGC's
2,816 of player and workspace, and it makes VGC's buffer slightly *smaller*
than FAP's 2,882.

### FAP is VGI with AY data in it

This is the comparison that settles the rest, and it was found last. **`.vgi`
is the same design as FAP, arrived at independently.** `vgm-packer`'s
`docs/vgi-format.md` describes eleven register columns, each compressed with a
byte-aligned LZSS over a 256-byte ring window with 8-bit offsets, decoded one
value per stream per frame - FAP's architecture exactly, on SN76489 registers
instead of AY ones. Both put **eleven bytes a frame** through the same kind of
coder, so the two files are as close to a controlled experiment as this repo
has.

If anything VGI's coder is the better of the two: literal runs to 128 against
FAP's 31, a dedicated RUN token for offset-1 held values, a length extension
byte to 255, and an optimal dynamic-programming parse where `Lzss.cpp` is
greedy.

| tune | FAP data | VGI v2 | v2 / FAP | VGI v3 | v3 / FAP |
|---|--:|--:|--:|--:|--:|
| Rhino, Acid Demo 21 | 5,600 | 10,069 | 1.80x | 7,718 | 1.38x |
| Targhan, Dead On Time | 3,240 | 6,460 | 1.99x | 4,610 | 1.42x |
| Tom&Jerry, Edge Grinder | 12,358 | 22,292 | 1.80x | 16,079 | 1.30x |
| Targhan, Orion Prime L4 | 7,092 | 10,530 | 1.48x | 8,126 | 1.15x |
| Targhan, Crtc | 16,022 | 28,043 | 1.75x | 21,438 | 1.34x |

The v2 ratios sit right on the 1.76-2.06x the section above measures for the AY
to SN conversion under a common coder. **With the coder held constant, the
entire difference is the representation** - and since VGI's coder is the
stronger, the representation gap is understated by those files, not overstated.

It is worth being precise about what the conversion does, because two obvious
explanations are both wrong. It is **not more bytes**: eleven a frame either
side. It is **not more changes**: the AY streams change 2.53 times a frame on
Acid Demo and the SN streams 2.40. What changes is how repeatable each change
is, and `r8` against `vol0` is the whole story in one line - the AY volume
changes on 43.3% of frames and costs 267 bytes, the SN volume changes on 19.3%
and costs 445. Fewer changes, dearer ones.

### And then VGI took most of it back

**That analysis was handed upstream and became `.vgi` v3** (`vgm-packer`
2026-09-06). If the SN's 4+6 period split is what spreads the entropy, stop
splitting: index each channel's period into a table the packer builds, and a
tone channel becomes one stream instead of two. Eight columns, a 2 KB ring
instead of 2.75 KB, and 21-29% off the file - the v3 column above.

**FAP's data advantage falls from 1.48-1.99x to 1.15-1.42x**, which is the
measurement working exactly as it said it would: the part of the gap that was
the period split is gone, and what is left is the volume streams and the
conversion's other losses.

And the fixed costs then decide it against FAP. `performance.md` measures VGI3
at 2,816 bytes of player and workspace against VGI v2's 3,584, where FAP needs
about 5,150 - it pays for `ay2sn` and a 2,882-byte decrunch buffer:

| tune | FAP total | VGI v2 total | VGI3 total |
|---|--:|--:|--:|
| Rhino, Acid Demo 21 | 10,750 | 13,653 | **10,534** |
| Targhan, Dead On Time | 8,390 | 10,044 | **7,426** |
| Tom&Jerry, Edge Grinder | **17,508** | 25,876 | 18,895 |
| Targhan, Orion Prime L4 | 12,242 | 14,114 | **10,942** |
| Targhan, Crtc | **21,172** | 31,627 | 24,254 |

So **FAP no longer wins the RAM against VGI** - it wins on the two longest
tunes and loses the other three, where before v3 it won all five by 1.7 to
10.5 KB. The one advantage FAP had over the format this project can already
play is now a split decision, and it is still paying ~1,300 cycles a frame for
it.

### How fast, really - and VGI is the anchor, not arithmetic

An earlier draft of this section estimated a 6502 FAP replay at 400-650 cycles
by counting instructions. **That was about half the true figure**, and VGI is
the measurement that says so: `vgm-player-bbc`'s `docs/vgi-player.md` cites a
decode-only study of the same eleven-stream ring LZSS at a **median of ~1,158
cycles looped and ~673 unrolled**. A per-stream state machine over eleven
streams does not cost forty cycles a stream.

So the honest figures for a 6502 FAP, beside what `performance.md` now measures
for everything else (mean and max are one call including the SN writes):

| | FAP (estimated from VGI) | AKL | AKM | VGI v2 | VGI3 |
|---|--:|--:|--:|--:|--:|
| replay | 700-1,200 | 963 | 1,291 | - | - |
| plus `ay2sn` | 1,690 | 1,690 | 1,690 | none - offline | none - offline |
| frame, mean | 2,400-2,900 | 2,494 | 2,546 | 1,512-1,581 | **1,236-1,331** |
| frame, max | narrow band | 3,900 | 4,489 | 2,866-3,007 | **2,020-2,314** |

**FAP's replay is about AKM's and dearer than AKL's, and it still owes the
spine.** VGI v2 was ~1,300 cycles a frame cheaper than FAP would be, and v3 is
another ~275 cheaper again, for the same reason FAP would have been quick: it
decodes fewer streams. What survives of FAP's speed argument is only the
*shape* - a narrow band - and VGI3 now has a narrower one, 2,020-2,314 against
AKM's 4,489-5,032 and VGC's 5,125-5,601.

### The route, if it is ever wanted

Not from the Z80 source. **`lib/vgiplayer.asm` in kieranhj's fork is already a
6502 implementation of FAP's architecture** - 545 bytes, 4 zero-page bytes, an
eleven-page ring - so a FAP player is that state machine re-pointed at FAP's
token encoding and header, emitting into `ay_regs`. That is a much smaller job
than transcribing 14 KB of cycle-padded Z80, and it is the only sane starting
point.

The Z80 player does not port in any case: `SKIP_NOPS` padding on every path, a
stabilisation loop, self-modifying relocation, `SP` as the source pointer,
`IXL`/`IYL`, `exx`. And there is no annotated source oracle - `SongToFap
--sourceProfile 6502acme` is accepted and then ignored, producing a
byte-identical 2,520-byte binary on `Acid_demo_07.aks`. What compensates is
that the reference **is** the `.ym` register log, subject to
`YmData::Optimize()`, which merges registers and sets delta flags before
crunching and has a lossy threshold mode (off by default).

### The conclusion

**Do not port FAP.** Against the tracker formats it loses the thing this
library optimises for: 1,000 to 6,000 bytes more RAM than AKM or AKL on every
tune, for a replay that is no cheaper than AKM's. Against VGI it used to have
one clear advantage - total RAM on all five tunes - and `.vgi` v3 has taken
three of those five back while staying ~1,300 cycles a frame cheaper. AKG
remains the better use of the same effort, because it buys fidelity and
coverage rather than trading one resource for another.

And the idea that looked worth stealing - crunch an **SN76489** log FAP-style,
so the conversion is offline and the frame cost is the decode alone - **was
already built, and it is VGI**. What FAP actually contributed was the
measurement of *why* VGI's files were twice the size of FAP's, which is the AY
to SN conversion and not anybody's compressor - and that measurement is now
worth 21-29% of a `.vgi` file, in `vgm-packer`, in v3.
