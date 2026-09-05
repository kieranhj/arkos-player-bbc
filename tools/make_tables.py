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


# ---------------------------------------------------------------- ay -> sn ---
def ym_sn_vol():
    """AY level (5-bit, 0-31) -> SN76489 attenuation (0 loud .. 15 silent).

    The YM/AY datasheet gives -0.75 dB per step on the 5-bit envelope
    ladder; the SN attenuates in -2 dB steps. So the attenuation for a
    level is (31 - level) * 0.75 / 2, TRUNCATED - rounding up would make
    a quiet note quieter than the AY intended, and truncating never does.
    Level 0 is silence, which is attenuation 15 rather than 11.
    """
    return [15] + [int((31 - n) * 0.75 / 2.0) for n in range(1, 32)]


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

    The SN has rates 0, 1, 2 (clock/512, /1024, /2048) plus rate 3, which
    clocks the noise from tone generator 3. Rate 3 IS NOT EMITTED YET -
    see docs/ay-to-sn.md, "What is still missing". These thresholds are
    the nearest fixed rate by period.
    """
    return [0] * 8 + [1] * 8 + [2] * 16


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
