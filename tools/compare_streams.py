#!/usr/bin/env python3
"""Hold a runtime SN76489 stream against ym2sn.py's offline one, frame by frame.

ym2sn.py is the bar. It does whole-song analysis - a priority bass channel,
sub-122 Hz notes synthesised with periodic noise, the hardware envelope
low-passed across the frame - where lib/ay2sn.asm sees one call at a time.
This says how much of that difference is left.

    python tools/verify/verify.py --player aky --bass 2 --song S --snf run.snf
    python bin/ym2sn.py song.ym -o ref.vgm
    python tools/compare_streams.py run.snf ref.vgm

Both streams are decoded to the chip's STATE at the end of each frame -
three tone periods, four attenuations and the noise byte - so a difference
in how often a register is rewritten does not show up as a difference in
what the chip was doing. Only what you could hear does.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sn2wav                                                    # noqa: E402


def states(frames):
    """The chip's state after each frame: [t0,t1,t2, a0,a1,a2,a3, noise]."""
    tone = [0, 0, 0]
    att = [15, 15, 15, 15]
    noise = 0
    latched = 0
    out = []
    for f in frames:
        for b in f:
            if b & 0x80:
                latched = (b >> 5) & 3
                if b & 0x10:
                    att[latched] = b & 15
                elif latched == 3:
                    noise = b & 15
                else:
                    tone[latched] = (tone[latched] & 0x3F0) | (b & 15)
            elif latched < 3:
                tone[latched] = (tone[latched] & 15) | ((b & 0x3F) << 4)
            elif latched == 3:
                noise = b & 15
        out.append(tone + att + [noise])
    return out


def load(path):
    if path.lower().endswith('.vgm'):
        return sn2wav.read_vgm(path)[0]
    return sn2wav.read_snf(path)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('runtime', help='.snf from verify.py --snf')
    ap.add_argument('reference', help='.vgm from ym2sn.py, or another .snf')
    args = ap.parse_args()

    a = states(load(args.runtime))
    b = states(load(args.reference))
    n = min(len(a), len(b))
    print('%d frames compared (%d and %d)' % (n, len(a), len(b)))

    audible = [0, 0, 0]         # frames where the reference has this channel on
    same_p = [0, 0, 0]
    same_v = [0, 0, 0]
    noise_same = noise_vol_same = noise_frames = 0
    bass_vol_bad = drum_vol_bad = 0
    drum_delta = {}
    for i in range(n):
        for ch in range(3):
            if b[i][3 + ch] == 15:
                continue        # silent in the reference: nothing to match
            audible[ch] += 1
            if a[i][ch] == b[i][ch]:
                same_p[ch] += 1
            if a[i][3 + ch] == b[i][3 + ch]:
                same_v[ch] += 1
        if b[i][6] != 15 or a[i][6] != 15:
            noise_frames += 1
            if a[i][7] == b[i][7]:
                noise_same += 1
            if a[i][6] == b[i][6]:
                noise_vol_same += 1
            elif b[i][7] == 3:
                bass_vol_bad += 1
            else:
                drum_vol_bad += 1
                drum_delta[a[i][6] - b[i][6]] =                     drum_delta.get(a[i][6] - b[i][6], 0) + 1

    print()
    print('             audible   period exact   volume exact')
    for ch in range(3):
        m = max(audible[ch], 1)
        print('  channel %d  %7d   %6.1f%%        %6.1f%%'
              % (ch, audible[ch], 100.0 * same_p[ch] / m, 100.0 * same_v[ch] / m))
    tot = max(sum(audible), 1)
    print('  ALL        %7d   %6.1f%%        %6.1f%%'
          % (sum(audible), 100.0 * sum(same_p) / tot, 100.0 * sum(same_v) / tot))
    print()
    print('  noise channel, %d sounding frames:' % noise_frames)
    print('     the noise byte (rate and feedback) identical on %d (%.1f%%)'
          % (noise_same, 100.0 * noise_same / max(noise_frames, 1)))
    print('     its volume identical on %d (%.1f%%)'
          % (noise_vol_same, 100.0 * noise_vol_same / max(noise_frames, 1)))
    if bass_vol_bad or drum_vol_bad:
        print('     of the rest: %d are the periodic bass, %d are drums'
              % (bass_vol_bad, drum_vol_bad))
    if drum_delta:
        # ym2sn mixes the noise at a share of each open channel's AMPLITUDE
        # (NOISE_MIX_SCALE); ay2sn takes the loudest open channel whole. So
        # our drums come out louder, and this says by how much. Negative is
        # a lower attenuation, which is louder.
        print('     drum loudness, ours minus ym2sn in SN steps (-2 dB each): %s'
              % dict(sorted(drum_delta.items())))

    # The bass: how often do the two agree that the noise channel is carrying
    # a note rather than a drum? That is the single decision B1 has to make
    # every call and ym2sn makes once for the whole song.
    both = ours = theirs = 0
    for i in range(n):
        p = a[i][7] == 3
        q = b[i][7] == 3
        ours += p
        theirs += q
        both += p and q
    print('  periodic bass (noise rate 3): ours %d frames, ym2sn %d, agreeing %d'
          % (ours, theirs, both))
    if theirs:
        print('  -> %.1f%% of ym2sn\'s periodic-bass frames are ours too'
              % (100.0 * both / theirs))


if __name__ == '__main__':
    main()
