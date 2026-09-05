#!/usr/bin/env python3
"""The SN76489's REGISTERS, frame by frame, against another build of ay2sn.

verify.py compares `ay_regs` - what the replay produced. That is the right
check for a replay and the wrong one for the conversion layer, because every
interesting thing ay2sn does happens after `ay_regs` is filled.

Comparing the SN write STREAM is wrong too, and this is the point of the tool:
the chip's tone and volume registers LATCH, so a converter is free to elide a
byte the register already holds. A write-through cache does exactly that, and
its stream is deliberately not the old one. What may not change is the state
the chip is left in. So this reconstructs the eight registers from the stream
and compares those, frame for frame.

It caught two real faults on the day it was written, neither of which a stream
diff or a cycle count would have shown:

  - packing the second tone byte through a lookup table clobbered Y, which
    still held the SN slot, so every volume went to the wrong register;
  - skipping the envelope generator when no channel uses it froze the phase,
    and two of the 39 corpus songs then resumed a SLOW envelope from the
    wrong place.

    python tools/verify/chip_state.py --player akl --song "…/EDGEA.SKS"
    python tools/verify/chip_state.py --corpus            # all 39 AKM songs

The baseline is git's copy of lib/ay2sn.asm at --baseline (default HEAD): the
working tree is assembled, then the baseline, then the working tree is put
back. It is restored even if the run fails.

Run from the REPO ROOT.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from py65.devices.mpu6502 import MPU                            # noqa: E402
from py65.memory import ObservableMemory                        # noqa: E402

import arkos                                                    # noqa: E402
import verify                                                   # noqa: E402

SPINE = os.path.join(ROOT, 'lib', 'ay2sn.asm')


def chip_states(song, player, frames, bass):
    """(state per frame, bytes written, mean cycles a call).

    The state is the eight SN registers: three tone periods, three tone
    volumes, the noise control and the noise volume. None means the register
    has never been written, which is itself a difference worth seeing.
    """
    env_base = (arkos.envelope_base(song) if player in ('akl', 'akm') else 8)
    img, lab, _, _ = verify.build(song, player, env_base)
    mem = ObservableMemory()
    for i, b in enumerate(img):
        mem[verify.LOAD + i] = b
    w = []
    mem.subscribe_to_write([0xFE4F], lambda a, v: w.append(v))
    mpu = MPU(memory=mem)
    RET = verify.RET

    def call(addr):
        sp = mpu.sp
        mem[0x100 + sp] = ((RET - 1) >> 8) & 0xFF
        mem[0x100 + ((sp - 1) & 0xFF)] = (RET - 1) & 0xFF
        mpu.sp = (sp - 2) & 0xFF
        mpu.pc = addr
        c0 = mpu.processorCycles
        while mpu.pc != RET:
            mpu.step()
        return mpu.processorCycles - c0

    mpu.a, mpu.x, mpu.y = verify.SIM_SONG & 0xFF, verify.SIM_SONG >> 8, 0
    call(lab['%s_init' % player])
    mem[lab['bass_mode']] = bass

    state, out, nbytes, cycles = {}, [], 0, 0
    for _ in range(frames):
        del w[:]
        cycles += call(lab['music_frame'])
        nbytes += len(w)
        i = 0
        while i < len(w):
            b = w[i]
            if not b & 0x80:            # a data byte with no latch: skip
                i += 1
                continue
            reg = (b >> 4) & 7
            if reg in (0, 2, 4) and i + 1 < len(w) and not w[i + 1] & 0x80:
                state[reg] = (b & 15) | (w[i + 1] << 4)
                i += 2
            else:
                state[reg] = b & 15
                i += 1
        out.append(tuple(state.get(r) for r in range(8)))
    return out, nbytes, cycles / float(frames)


def compare(song, player, frames, bass, baseline):
    now, n_now, c_now = chip_states(song, player, frames, bass)
    mine = open(SPINE, 'rb').read()
    old = subprocess.run(['git', 'show', '%s:lib/ay2sn.asm' % baseline],
                         cwd=ROOT, capture_output=True).stdout
    if not old:
        raise SystemExit('could not read lib/ay2sn.asm at %s' % baseline)
    open(SPINE, 'wb').write(old)
    try:
        was, n_was, c_was = chip_states(song, player, frames, bass)
    finally:
        open(SPINE, 'wb').write(mine)
    bad = [f for f in range(frames) if now[f] != was[f]]
    return bad, (n_was, n_now), (c_was, c_now), (now, was)


def corpus_songs():
    """The songs lib/akmplayer.asm is verified on, as paths."""
    out = []
    listing = os.path.join(HERE, 'akm_known_good.txt')
    for line in open(listing):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        for d in ('ArkosTracker2', 'ArkosTracker3', 'STarKos', '128',
                  'Wyz', 'VT2', 'Mod', 'Midi'):
            c = os.path.join(arkos.AT3, 'songs', d, line)
            if os.path.exists(c):
                out.append(c)
                break
        else:
            c = os.path.join(ROOT, 'songs', line)
            if os.path.exists(c):
                out.append(c)
            else:
                sys.stderr.write('not found, skipped: %s\n' % line)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--player', default='akl', choices=('akl', 'aky', 'akm'))
    ap.add_argument('--song', default=verify.DEFAULT_SONG)
    ap.add_argument('--frames', type=int, default=900)
    ap.add_argument('--bass', type=int, default=2, choices=(0, 1, 2))
    ap.add_argument('--baseline', default='HEAD',
                    help='the git revision to compare lib/ay2sn.asm against')
    ap.add_argument('--corpus', action='store_true',
                    help='every song in akm_known_good.txt, as AKM')
    args = ap.parse_args()

    songs = corpus_songs() if args.corpus else [args.song]
    player = 'akm' if args.corpus else args.player
    same = diff = 0
    tot_was = tot_now = 0.0
    for song in songs:
        try:
            bad, (n_was, n_now), (c_was, c_now), (now, was) = compare(
                song, player, args.frames, args.bass, args.baseline)
        except Exception as e:                          # noqa: BLE001
            sys.stderr.write('  FAILED %s: %s\n' % (os.path.basename(song), e))
            diff += 1
            continue
        ok = not bad
        same += ok
        diff += not ok
        tot_was += c_was
        tot_now += c_now
        print('  %-52s %-4s %6.0f -> %6.0f (%+5.1f%%)  bytes %5d -> %5d'
              % (os.path.basename(song)[:52], 'OK' if ok else 'DIFF',
                 c_was, c_now, 100.0 * (c_now - c_was) / c_was, n_was, n_now))
        if bad:
            f = bad[0]
            print('     first difference frame %d of %d:' % (f, args.frames))
            print('       now %s' % (now[f],))
            print('       was %s' % (was[f],))
    n = same + diff
    print()
    print('%d identical, %d differ, over %d frames each.' % (same, diff, args.frames))
    if same:
        print('mean %.0f -> %.0f cycles a call (%+.1f%%)'
              % (tot_was / same, tot_now / same,
                 100.0 * (tot_now - tot_was) / tot_was))
    return 1 if diff else 0


if __name__ == '__main__':
    sys.exit(main())
