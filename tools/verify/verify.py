#!/usr/bin/env python3
"""Verify and measure the players in lib/, against something independent.

Nothing here is checked against itself. The chain is:

  1. akl_reference.py, a Python transcription of Arkos's own Z80 player, is
     checked against a .ym: the AY register log SongToYm.exe produces by
     running Arkos's FULL player over the same song. That oracle is outside
     this project entirely.
  2. The 6502 player is run in py65 and its ay_regs compared to the
     reference, frame for frame.
  3. The per-frame cost is reported, per 50 Hz field and per 25 Hz frame.
  4. Optionally the SN76489 writes are captured to an .snf for
     tools/sn2wav.py - the only way to judge what is not a correctness
     question.

For AKY there is no Python transcription and none is needed: AKY is close
to a register stream, so the 6502 player's ay_regs are compared straight
against the oracle.

Run from the REPO ROOT (beebasm resolves INCLUDEs from the working directory):

    python tools/verify/verify.py
    python tools/verify/verify.py --player aky --song songs/Acid_demo_21.aks
    python tools/verify/verify.py --snf build/runtime.snf     # and capture

Needs beebasm, `pip install py65 numpy`, and an Arkos install for the
oracle (AT3 for AKY/SongToYm, AT2 for the AKL export - see docs/format-akl.md).
Without an oracle it still runs check 2 and says which check it skipped.
"""

import argparse
import os
import re
import struct
import subprocess
import sys

import numpy as np
from py65.devices.mpu6502 import MPU
from py65.memory import ObservableMemory

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
BUILD = os.path.join(HERE, 'build')
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import akl_reference                                            # noqa: E402
import akm_reference                                            # noqa: E402
import arkos                                                    # noqa: E402
import sn2wav                                                   # noqa: E402

BEEB = os.path.dirname(os.path.dirname(ROOT))
HOME = os.path.expanduser('~')
AT3 = os.environ.get('ARKOS3_HOME',
                     os.path.join(HOME, 'OneDrive', 'Trackers', 'ArkosTracker3'))
AT2 = os.environ.get('ARKOS2_HOME',
                     os.path.join(HOME, 'OneDrive', 'Trackers', 'Arkos Tracker 2'))

DEFAULT_SONG = os.path.join(ROOT, 'songs', 'Acid_demo_21.aks')

SIM_SONG = 0x4000           # where the sim plays the song from
LOAD = 0x1100               # the sim image's ORG
RET = 0x9000                # sentinel return address
FRAME_BUDGET = 79872        # a 25 Hz game frame, 2 MHz cycles


def find(*cands):
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def beebasm():
    return find(os.path.join(ROOT, 'bin', 'beebasm.exe'),
                os.path.join(BEEB, 'Bin', 'beebasm.exe')) or 'beebasm'


def song_to_ym():
    """AT3's is the current one; AT2's (or nova-invite's copy) is the fallback."""
    return find(os.path.join(AT3, 'tools', 'SongToYm.exe'),
                os.path.join(AT2, 'tools', 'SongToYm.exe'),
                os.path.join(BEEB, 'Repos', 'nova-invite', 'bin', 'SongToYm.exe'))


def export_song(song, player, addr):
    """Tracker data at `addr`, in the format `player` replays."""
    out = os.path.join(BUILD, 'song.bin')
    os.makedirs(BUILD, exist_ok=True)
    if player == 'akl':
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'export_akl.py'),
                        song, '--addr', hex(addr), '-o', out],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    elif player == 'akm':
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'export_akm.py'),
                        song, '--addr', hex(addr), '-o', out],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    else:
        exe = os.path.join(AT3, 'tools', 'SongToAky.exe')
        if not os.path.exists(exe):
            raise SystemExit('SongToAky.exe not found at %s (Arkos Tracker 3)' % exe)
        r = subprocess.run([exe, '-s', '1', '-bin', '-adr', hex(addr), song, out],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit('SongToAky failed (%d)' % r.returncode)
    return out, os.path.getsize(out)


def aky_psgs(path):
    """How many PSGs the AKY export carries. Three channels make a PSG."""
    return (open(path, 'rb').read()[1] + 2) // 3


def build(song, player, env_base):
    """Export the song at SIM_SONG and assemble the real lib/ sources around it."""
    path, size = export_song(song, player, SIM_SONG)
    labels = os.path.join(BUILD, 'labels.txt')
    subprocess.run([beebasm(), '-i', 'tools/verify/sim.asm',
                    '-D', 'SIM_SONG=%d' % SIM_SONG,
                    '-D', 'PLAYER_AKY=%d' % (player == 'aky'),
                    '-D', 'PLAYER_AKM=%d' % (player == 'akm'),
                    '-D', 'ENV_BASE=%d' % env_base,
                    '-d', '-labels', labels],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    lab = eval(re.sub(r'(\d+)L', r'\1', open(labels).read()))[0]
    return open(os.path.join(BUILD, 'Sim'), 'rb').read(), lab, path, size


def read_ym(path):
    """A YM5/YM6 interleaved log: (frame count, one byte column per register)."""
    d = open(path, 'rb').read()
    assert d[:4] in (b'YM5!', b'YM6!'), 'not a YM5/YM6 file'
    o = 12
    n, = struct.unpack('>I', d[o:o + 4])
    o += 4 + 4 + 2 + 4 + 2 + 4 + 2
    for _ in range(3):
        o = d.index(b'\0', o) + 1
    data = d[o:o + 16 * n]
    return n, [data[r * n:(r + 1) * n] for r in range(16)]


def oracle(song):
    """The YM register log from Arkos's own player, or None if unavailable."""
    exe = song_to_ym()
    if not exe:
        return None, None
    ym = os.path.join(BUILD, os.path.basename(song) + '.ym')
    if not os.path.exists(ym):
        r = subprocess.run([exe, '-p', '1', song, ym], capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout + r.stderr)
            return None, exe
    return read_ym(ym), exe


def compare_audible(frames, cols, n):
    """Frames against the YM oracle, comparing only what can be HEARD.

    SongToYm zeroes R6 when nothing has the noise open and R11/R12 when
    nothing uses the envelope, and Arkos's player leaves a silent channel's
    tone-disable bit alone - so a raw register diff reads as badly wrong and
    is not. This function is where that judgement lives.
    """
    bad = {}
    for f in range(n):
        ym = [cols[i][f] for i in range(14)]
        us = frames[f]
        for ch in range(3):
            vy, vu = ym[8 + ch], us[8 + ch]
            if vy != vu:
                bad['ch%d volume' % ch] = bad.get('ch%d volume' % ch, 0) + 1
            tone_ym = not (ym[7] >> ch) & 1
            noi_ym = not (ym[7] >> (3 + ch)) & 1
            if not ((vy & 15 or vy & 16) and (tone_ym or noi_ym)):
                continue                                # inaudible either way
            if tone_ym:
                py = ym[2 * ch] | ((ym[2 * ch + 1] & 15) << 8)
                pu = us[2 * ch] | ((us[2 * ch + 1] & 15) << 8)
                if py != pu:
                    bad['ch%d period' % ch] = bad.get('ch%d period' % ch, 0) + 1
            if noi_ym and ym[6] != us[6]:
                bad['noise period'] = bad.get('noise period', 0) + 1
        if any(ym[8 + c] & 16 for c in range(3)):
            if ym[11] != us[11] or ym[12] != us[12]:
                bad['env period'] = bad.get('env period', 0) + 1
            if cols[13][f] != 255 and cols[13][f] != us[13]:
                bad['env shape'] = bad.get('env shape', 0) + 1
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--player', default='akl', choices=('akl', 'aky', 'akm'))
    ap.add_argument('--song', default=DEFAULT_SONG,
                    help='an .sks or .aks Arkos song (default: songs/Acid_demo_21.aks)')
    ap.add_argument('--frames', type=int, default=0,
                    help='stop after N frames (default: the whole tune)')
    ap.add_argument('--snf', help='also capture the SN76489 writes to this .snf')
    ap.add_argument('--bass', type=int, default=0, choices=(0, 1, 2),
                    help='bass_mode: 0 octave-shift, 1 software (needs a VIA, '
                         'so it does nothing here), 2 periodic noise')
    args = ap.parse_args()

    if not os.path.exists(args.song):
        raise SystemExit('song not found: %s' % args.song)

    # AKL's envelope pair belongs to the song; the reference must use the
    # same value as the player or the comparison is meaningless.
    env_base = (arkos.envelope_base(args.song)
                if args.player in ('akl', 'akm') else 8)
    akl_reference.ENV_BASE = env_base
    akm_reference.ENV_BASE = env_base
    img, lab, songpath, songsize = build(args.song, args.player, env_base)
    print('song:    %s' % os.path.relpath(args.song, ROOT))
    print('format:  %s, %d bytes' % (args.player.upper(), songsize))
    if args.player in ('akl', 'akm'):
        print('ENV_BASE: %d' % env_base)
    if args.player == 'aky':
        n_psg = aky_psgs(songpath)
        if n_psg > 1:
            print('         %d PSGs: playing the FIRST, ignoring %d more channels'
                  % (n_psg, 3 * (n_psg - 1)))
    print('code:    %d bytes (&%04X-&%04X), player + converter'
          % (lab['all_end'] - lab['start'], lab['start'], lab['all_end']))

    mem = ObservableMemory()
    for i, b in enumerate(img):
        mem[LOAD + i] = b
    writes = []
    mem.subscribe_to_write([0xFE4F], lambda a, v: writes.append(v))
    mpu = MPU(memory=mem)

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

    # Both players are handed the base of the exported data; aky_init
    # parses the AKY header itself rather than trusting a caller to.
    init = lab['%s_init' % args.player]
    mpu.a, mpu.x, mpu.y = SIM_SONG & 0xFF, SIM_SONG >> 8, 0
    call(init)

    # AKL's linker encodes a transposition only when it CHANGES and the
    # player starts at zero, so a song whose FIRST position is transposed
    # depends on AT2's exporter writing it there - and WON4 shows it does
    # not always. akl_init clears t_transp and does not read the linker, so
    # a host sets it here; example/demo.asm does exactly this, and
    # export_akl.py --check refuses an export that needs it. The reference
    # gets the same treatment, because both are the HOST's job, not the
    # format's. See docs/format-akl.md.
    transp = (0, 0, 0)
    if args.player == 'akl':
        transp = arkos.initial_transpositions(args.song)
        if transp != (0, 0, 0):
            for i, v in enumerate(transp):
                mem[lab['t_transp'] + i] = v & 0xFF
            print('transp:  position 0 is %s, which the AKL export does not'
                  % list(transp))
            print('         carry - set into t_transp, as a host must')

    # The bass voice. Mode 1 is interrupt-driven and py65 has no VIA, so it
    # cannot be exercised here at all - only jsbeeb sees it. Mode 2, the
    # periodic-noise voice, is pure ay2sn and runs here exactly as it runs
    # on the machine, which is why it gets checks 5 and 6 below and the
    # software voice never could.
    mem[lab['bass_mode']] = args.bass
    print('bass:    mode %d (%s)' % (args.bass,
          ('octave shift', 'software - NOT simulated, needs a VIA',
           'periodic noise')[args.bass]))

    ym, ymexe = oracle(args.song)
    if ym:
        # The rate the song is AUTHORED for. It is not in the exported data:
        # the player replays as often as the host calls it, so the host has
        # to know this and call at this rate. Most songs are 50 Hz; some are
        # not, and one that is not plays at the wrong speed silently.
        try:
            rate = arkos.ym_header(os.path.join(
                BUILD, os.path.basename(args.song) + '.ym'))[2] or 50
        except (OSError, ValueError):
            rate = 50
        print('replay:  %d Hz - %d calls, %.1f seconds of music'
              % (rate, ym[0], ym[0] / float(rate)))
        if rate != 50:
            print('         NOT 50 Hz: a host running off VSync must call the')
            print('         player every %d fields, not every field.'
                  % int(round(50.0 / rate)))

    n = args.frames or (ym[0] if ym else 5000)
    if ym:
        n = min(n, ym[0])

    ref = None
    if args.player == 'akl':
        ref = akl_reference.Player(open(songpath, 'rb').read(), SIM_SONG)
        for t, v in zip(ref.tr, transp):
            t.transp = v & 0xFF
    elif args.player == 'akm':
        ref = akm_reference.Player(open(songpath, 'rb').read(), SIM_SONG)

    regs = lab['ay_regs']
    perframe, captured, got_frames, ref_frames = [], [], [], []
    claimed = []                    # which channel took the bass voice, or 255
    mismatch, first = 0, None
    for f in range(n):
        del writes[:]
        perframe.append(call(lab['music_frame']))
        captured.append(list(writes))
        claimed.append(mem[lab['bass_chan']])
        got = [mem[regs + i] for i in range(14)]
        got_frames.append(got)
        if ref is not None:
            want = list(ref.play())
            ref_frames.append(list(want))       # raw R13, for the oracle check
            # ...but the 6502 reports 255 on a frame where R13 was not re-sent
            want[13] = ref.r13_sent if ref.r13_sent is not None else 255
            if got != want:
                mismatch += 1
                if first is None:
                    first = (f, got, want)

    print()
    if ref is not None:
        print('1. the 6502 player against %s_reference.py, over %d frames:'
              % (args.player, n))
        if mismatch:
            print('   *** DIFFERS on %d frames ***' % mismatch)
            print('   first: frame %d\n     6502 %s\n     ref  %s' % first)
        else:
            print('   IDENTICAL on every frame')
    else:
        print('1. no Python reference for %s - the 6502 is compared straight'
              % args.player.upper())
        print('   to the oracle below, which for a register-stream format is')
        print('   the stronger check anyway.')

    print()
    print('2. against the YM oracle (Arkos\'s own player):')
    if ym is None:
        print('   SKIPPED - no SongToYm.exe found')
    else:
        print('   oracle: %s' % ymexe)
        subject = ref_frames if ref is not None else got_frames
        what = (('%s_reference.py' % args.player) if ref is not None
                else 'the 6502 player')
        bad = compare_audible(subject, ym[1], min(n, ym[0]))
        print('   %s: audible mismatches: %s' % (what, bad if bad else 'NONE'))

    a = np.array(perframe)
    pair = a[:-1] + a[1:]
    print()
    print('3. cost, cycles @ 2 MHz:')
    print('   per 50 Hz field:   min %d  mean %.0f  p99 %d  max %d'
          % (a.min(), a.mean(), np.percentile(a, 99), a.max()))
    print('   per 25 Hz frame:   min %d  mean %.0f  p99 %d  max %d  (%.1f%% of %d)'
          % (pair.min(), pair.mean(), np.percentile(pair, 99), pair.max(),
             100.0 * pair.max() / FRAME_BUDGET, FRAME_BUDGET))
    print('   SN writes a frame: min %d  mean %.1f  max %d'
          % (min(len(w) for w in captured),
             sum(len(w) for w in captured) / float(len(captured)),
             max(len(w) for w in captured)))

    # How much of the tune falls off the bottom of the SN76489.
    #
    # The SN's period is ten bits, so its lowest note is 4 MHz / (32 * 1023)
    # = 122 Hz. ay2sn halves an AY period that will not fit, an octave at a
    # time - so every bass note below that comes out an OCTAVE HIGH. It is
    # the single most audible thing this conversion does wrong, and a tune
    # with a tuned bass will show it here.
    low, audible, rescued = 0, 0, 0
    for got, claim in zip(got_frames, claimed):
        for ch in range(3):
            vol = got[8 + ch]
            if not (vol & 31) or (got[7] >> ch) & 1:
                continue                        # silent, or tone disabled
            audible += 1
            if (got[2 * ch] | ((got[2 * ch + 1] & 15) << 8)) > 511:
                low += 1
                if claim == ch:
                    rescued += 1
    print()
    print("4. below the SN76489's 122 Hz floor:")
    if audible:
        print('   %d of %d audible channel-frames (%.1f%%)'
              % (low, audible, 100.0 * low / audible))
        if low:
            print('   a bass voice took %d of them (%.1f%%); the other %d came'
                  % (rescued, 100.0 * rescued / low, low - rescued))
            print('   out an octave high. See docs/ay-to-sn.md.')
            if args.bass == 1:
                print('   NOTE: mode 1 needs a VIA and py65 has none, so this')
                print('   is measuring the fallback, not the software voice.')
    else:
        print('   nothing audible in this range')

    # ---- the periodic-noise bass, end to end ------------------------------
    #
    # Checks 1 and 2 cannot see any of this: they compare ay_regs, and the
    # bass happens BELOW that line, in ay2sn. So this decodes what actually
    # reached the chip and holds it against ym2sn.py's own arithmetic - the
    # SN's periodic noise runs at a fifteenth of tone generator 3, so the
    # period is round(2 * ay_period / 15), which is ym2sn's int(round()).
    if args.bass == 2:
        print()
        print('5. the periodic-noise bass, decoded from the SN writes:')
        bad_period = bad_noise = bad_vol = redundant = 0
        claims = 0
        latched = None
        tone2 = [None, None]        # lo nibble, hi 6 bits
        noise_byte = None
        for got, claim, ws in zip(got_frames, claimed, captured):
            prev_noise = noise_byte
            for b in ws:
                if b & 0x80:
                    latched = (b >> 5) & 3
                    if latched == 3 and not (b & 0x10):
                        noise_byte = b
                        if b == prev_noise:
                            redundant += 1      # a needless LFSR reset
                        prev_noise = b
                    elif latched == 2 and not (b & 0x10):
                        tone2[0] = b & 15
                    elif latched == 2 and (b & 0x10):
                        tone2vol = b & 15
                elif latched == 2:
                    tone2[1] = b & 0x3F
            if claim > 2:
                continue
            claims += 1
            ay = got[2 * claim] | ((got[2 * claim + 1] & 15) << 8)
            want = int(round(2 * ay / 15.0))
            if tone2[0] is None or tone2[1] is None:
                bad_period += 1
            elif (tone2[1] << 4) | tone2[0] != want:
                bad_period += 1
            if noise_byte != 0xE3:
                bad_noise += 1
            if tone2vol != 15:
                bad_vol += 1        # the clock slot has to be silent
        if not claims:
            print('   the voice was never claimed in this tune')
        else:
            print('   claimed on %d of %d calls' % (claims, n))
            print("   tone 3 period == ym2sn's round(2*p/15): %s"
                  % ('every one' if not bad_period else '*** %d WRONG ***' % bad_period))
            print('   noise byte &E3 (periodic, rate 3):        %s'
                  % ('every one' if not bad_noise else '*** %d WRONG ***' % bad_noise))
            print('   the clocking tone slot silent:            %s'
                  % ('every one' if not bad_vol else '*** %d WRONG ***' % bad_vol))
            print('   redundant noise writes (each resets the LFSR): %d' % redundant)


    if args.snf:
        os.makedirs(os.path.dirname(os.path.abspath(args.snf)), exist_ok=True)
        sn2wav.write_snf(args.snf, captured)
        print()
        print('   %s: %d frames - render it with tools/sn2wav.py'
              % (args.snf, len(captured)))

    return 1 if mismatch else 0


if __name__ == '__main__':
    sys.exit(main())
