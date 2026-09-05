#!/usr/bin/env python3
"""Generate the two lookup tables the library assembles, from their sources.

Neither was reproducible before this: both were committed as .asm with no
generator, so nobody could say where a number came from or change one.

    lib/akl_periods.asm    the AY note period table, 128 notes, lo/hi
                           EXTRACTED from reference/PlayerLightweight.asm,
                           which is where Arkos's own player keeps it. Not
                           recomputed - taking Arkos's numbers means the
                           replay cannot disagree with Arkos about pitch.

    lib/ay2sn_tables.asm   the four tables lib/ay2sn.asm needs:
                             ym_sn_vol      AY 5-bit level -> SN attenuation
                             env_shape      the envelope's 32-step ramp
                             ay_noise_rate  AY noise period -> SN noise rate
                             env_recip_lo/hi  1 / envelope period, 16.16

Run it with --check to prove the committed files still match, which is what
CI would do if this repo had any:

    python tools/make_tables.py            # rewrite both files
    python tools/make_tables.py --check    # verify, change nothing
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LIB = os.path.join(ROOT, 'lib')
PLAYER_Z80 = os.path.join(ROOT, 'reference', 'PlayerLightweight.asm')
PLAYER_AKM = os.path.join(ROOT, 'reference', 'PlayerAkm_z80.asm')

# The two chips. The AY figure is the CPC's, which is what the songs this
# library plays were written for; the SN figure is the BBC's. Everything
# below is derived from these rather than from written-down thresholds.
AY_CLOCK = 1000000
SN_CLOCK = 4000000


def _shape(text):
    """A file's labels and bytes, ignoring comments and layout."""
    return re.findall(r'^\.(\w+)|&([0-9a-fA-F]{2})', text, re.M)


def rows(name, vals, per=16):
    out = ['.%s' % name]
    for i in range(0, len(vals), per):
        out.append('    EQUB ' + ', '.join('&%02x' % v for v in vals[i:i + per]))
    return out


# ---------------------------------------------------------------- periods ---
def periods():
    """The 128 CPC note periods, lifted out of Arkos's own Z80 player.

    The table sits under PLY_LW_PeriodTable, inside `IFDEF
    PLY_LW_HARDWARE_CPC` - a 1 MHz PSG, which is what the songs this
    library plays were written for.
    """
    src = open(PLAYER_Z80, encoding='utf-8', errors='replace').read()
    i = src.index('PLY_LW_PeriodTable:')
    j = src.index('PLY_LW_HARDWARE_CPC', i)
    vals = []
    for line in src[j:].splitlines()[1:]:
        s = line.strip()
        if s.startswith(';'):
            continue
        if not s.lower().startswith('dw '):
            if vals:
                break
            continue
        for n in re.findall(r'\d+', s.split(';')[0][3:]):
            vals.append(int(n))
        if len(vals) >= 128:
            break
    if len(vals) != 128:
        raise SystemExit('found %d periods in %s, expected 128'
                         % (len(vals), PLAYER_Z80))
    return (['\\ The AY period for each of the 128 notes, taken verbatim from',
             '\\ reference/PlayerLightweight.asm (PLY_LW_PeriodTable, the 1 MHz',
             '\\ CPC PSG). Regenerate with tools/make_tables.py.']
            + rows('per_lo', [v & 0xFF for v in vals], 12)
            + rows('per_hi', [v >> 8 for v in vals], 12))


def akm_periods():
    """AKM's 256 note periods - DERIVED, because AKM's player derives them.

    AKL ships a full 128-note table and this repo lifts it verbatim, so the
    replay cannot disagree with Arkos about pitch. AKM cannot be treated that
    way: it ships only TWELVE entries, octave 0, and its player computes every
    other octave at run time by halving with `srl h : rr l`, rounding up if the
    last bit shifted out was set.

    That is not the same function as Arkos's own note table. They disagree on
    the six notes where the halving lands exactly on .5 - 18, 21, 23, 28, 49
    and 56 - where AKM comes out one HIGHER. So lib/akl_periods.asm cannot be
    reused: a player using it would disagree with the player it is a port of,
    and the difference would read as Arkos's documented plus-or-minus-one
    tolerance rather than as a fault.

    This generates the table by running AKM's own arithmetic, so the table is
    provably the loop it replaces (KC, 2026-09-05: "just build the table").
    256 entries because the note index is base note + instrument arpeggio +
    arpeggio table value, added 8-bit with no mask, so every value 0-255 has
    to mean something. Above note ~110 the shifts reach zero, which is what
    Arkos's player does too.
    """
    src = open(PLAYER_AKM, encoding='utf-8', errors='replace').read()
    i = src.index('PLY_AKM_HARDWARE_PSG_1000000_HZ')
    j = src.index('PLY_AKM_PeriodTable:', i)
    line = src[j:].splitlines()[1]
    octave0 = [int(n) for n in re.findall(r'\d+', line.split(';')[0])]
    if len(octave0) != 12:
        raise SystemExit('found %d octave-0 periods in %s, expected 12'
                         % (len(octave0), PLAYER_AKM))

    vals = []
    for n in range(256):
        a, octave = n, 0
        while a >= 12:                      # inc b / sub c / jr nc
            a -= 12
            octave += 1
        p, carry = octave0[a], 0
        for _ in range(octave):
            carry = p & 1                   # srl h / rr l
            p >>= 1
        if octave and carry:                # jr nc / inc hl
            p += 1
        vals.append(p & 0xFFFF)

    return ([r'\ AKM note periods, 256 notes, lo/hi. NOT the same table as',
             r'\ lib/akl_periods.asm: AKM ships twelve octave-0 periods and',
             r'\ halves them at run time, which disagrees with Arkos own',
             r'\ 128-note table on six notes (18, 21, 23, 28, 49, 56),',
             r'\ where AKM is one HIGHER. Generated by running AKM own',
             r'\ arithmetic over the octave-0 row in',
             r'\ reference/PlayerAkm_z80.asm - so the table is provably',
             r'\ the loop it replaces. Regenerate with tools/make_tables.py.']
            + rows('akm_per_lo', [v & 0xFF for v in vals], 16)
            + rows('akm_per_hi', [v >> 8 for v in vals], 16))


# ---------------------------------------------------------------- ay -> sn ---
def ym_sn_vol():
    """AY level (5-bit, 0-31) -> SN76489 attenuation (0 loud .. 15 silent).

    ym2sn.py's default: 15 - ((level + 1) >> 1), a plain halving of the
    5-bit level onto the SN's 4-bit attenuator.

    This is NOT the dB-faithful mapping, and the dB-faithful one is what
    was here before: the AY's ladder steps -0.75 dB and the SN's -2 dB, so
    (31 - level) * 0.75 / 2 truncated, which puts the AY's 23 dB of range
    into SN attenuations 0-11 and never makes a note quieter than the AY
    intended. That is the more correct arithmetic and it is available in
    ym2sn as -t, where it is marked *Experimental*.

    The halving is what every SN76489 stream anyone has actually listened
    to was made with, and it uses the chip's full 0-14 instead of stopping
    at 11 - so a quiet note is genuinely quiet and a fade reaches silence.
    Measured against ym2sn's own output for the same tune, this plus the
    4-bit widening in lib/ay2sn.asm takes Rhino's Acid Demo from 23.5% of
    tone volumes identical to 100.0%, and EDGEA from 28.7% to 97.4% (the
    rest of EDGEA being the hardware envelope). KC's call, 2026-09-05;
    docs/fidelity-plan.md, "The volume curve".

    Level 0 is silence either way, which is attenuation 15.
    """
    return [15 - ((min(n + 1, 31) >> 1) & 15) for n in range(32)]


def env_shape():
    """The hardware envelope's level at each of its 32 steps.

    lib/ay2sn.asm SAMPLES the envelope once a frame (see docs/ay-to-sn.md
    for why that is not what the offline chain does), and this is the ramp
    it samples: a straight 0..31 saw. ENV_BASE in the players compensates
    for AKL only being able to encode shapes 8 and 0xa.
    """
    return list(range(32))


def ay_noise_rate():
    """AY 5-bit noise period -> one of the SN's three fixed noise rates.

    The SN's rates 0, 1 and 2 clock the noise at SN_CLOCK/512, /1024 and
    /2048; rate 3 clocks it from tone generator 3 instead, which is the
    periodic-noise bass and never a drum (see lib/ay2sn.asm). So a drum
    picks one of three, and this is which.

    NEAREST BY FREQUENCY, which is what ym2sn.py does. The table used to
    be [0]*8 + [1]*8 + [2]*16 - thresholds at 8 and 16, described as
    "nearest by period", and it was neither: nearest by period puts them
    at 12 and 24 and nearest by frequency at 10.7 and 21.3. Nine entries
    changed (AY periods 8-10 and 16-21), and on EDGEA that is 1,088 of
    3,020 noise calls, 36%. Across the 75-song corpus the median song
    changes on 1% of its noise calls and 17 of the 75 on more than 20%
    (tools/survey_tunes.py, the "rate diff" column).

    Frequency rather than period because that is the domain the ear hears
    noise brightness in; taking the log of it instead moves one entry
    (period 11), and ym2sn's linear choice is kept for exact parity with
    the reference chain.
    """
    sn = [SN_CLOCK / (32.0 * 16 * (1 << r)) for r in range(3)]
    # the AY treats noise period 0 as 1
    return [min(range(3), key=lambda r: abs(AY_CLOCK / (16.0 * max(n, 1)) - sn[r]))
            for n in range(32)]


def env_recip():
    """The envelope phase step per 50 Hz field, for each envelope period.

    ay2sn keeps a 16-bit phase, adds this every field, and takes the top
    five bits of it (the high byte, three LSRs) as the position in the
    32-step ramp. So a COMPLETE envelope cycle is 65536 phase units.

    An AY envelope of period p takes 256 * p PSG clocks per cycle, and the
    PSG runs at 1 MHz, so in one 50 Hz field it completes 78.125 / p
    cycles - a step of 65536 * 78.125 / p = 5120000 / p phase units.

    At small periods that is many whole cycles per field, and only the
    remainder is visible, so the table is 5120000 / p TRUNCATED and then
    taken modulo 65536. That wrap is why the values look unordered: the
    step for period 4 (34816) is larger than the step for period 3 (2730).
    """
    lo, hi = [], []
    for p in range(256):
        v = 0 if p == 0 else int(5120000.0 / p) & 0xFFFF
        lo.append(v & 0xFF)
        hi.append(v >> 8)
    return lo, hi


def ay2sn_tables():
    lo, hi = env_recip()
    return (rows('ym_sn_vol', ym_sn_vol())
            + rows('env_shape', env_shape())
            + rows('ay_noise_rate', ay_noise_rate())
            + rows('env_recip_lo', lo)
            + rows('env_recip_hi', hi))


# -------------------------------------------------------------------- main ---
TABLES = {
    'lib/akl_periods.asm': periods,
    'lib/akm_periods.asm': akm_periods,
    'lib/ay2sn_tables.asm': ay2sn_tables,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true',
                    help='compare against the committed files, write nothing')
    args = ap.parse_args()

    bad = 0
    for rel, fn in TABLES.items():
        path = os.path.join(ROOT, rel)
        text = '\n'.join(fn()) + '\n'
        if args.check:
            have = open(path, encoding='utf-8').read() if os.path.exists(path) else ''
            # Compare the DATA, not the file: comments and row widths are
            # presentation, the bytes and the label order are the contract.
            same = _shape(have) == _shape(text)
            print('%-26s %s' % (rel, 'matches' if same else '*** DIFFERS ***'))
            bad += 0 if same else 1
        else:
            open(path, 'w', encoding='utf-8').write(text)
            print('%-26s written, %d lines' % (rel, text.count('\n')))
    return bad


if __name__ == '__main__':
    sys.exit(main())
