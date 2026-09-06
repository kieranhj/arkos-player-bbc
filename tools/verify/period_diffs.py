"""How BIG are the period disagreements with Arkos, not just how many?

`verify.py` counts audible mismatches; it does not say by how much. That
matters, because Arkos documents a plus-or-minus-one difference in the
volume/pitch effects between its PC side and its Z80 player, and a count on
its own cannot tell that apart from a wrong note. This prints the magnitude
histogram instead.

What it caught: Tom&Jerry's WON4 - Edge Grinder's end-game tune - disagrees
with Arkos on 216 channel-frames that are NOT the documented plus-or-minus
one. They are 108 frames off by 180 period units on channel 1 and 108 off by
476 on channel 2: audible wrong pitches, about 3.3% of the tune. Both AT2's
and AT3's SongToYm produce the identical histogram, so the two Arkos versions
agree with each other and disagree with us - unlike EDGEA, where they disagree
with each other. See docs/format-akl.md, "WON4 plays wrong notes".

    python tools/verify/period_diffs.py <song.sks> [--player akl|akm]
    ARKOS3_HOME=/nonexistent python tools/verify/period_diffs.py <song.sks>
"""
import sys, os, argparse, collections
sys.path.insert(0, 'tools')
sys.path.insert(0, 'tools/verify')
import verify                                                   # noqa: E402
import akl_reference, akm_reference                             # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument('song')
ap.add_argument('--player', default='akl', choices=('akl', 'akm'))
args = ap.parse_args()

ym, exe = verify.oracle(args.song)
if not ym:
    sys.exit('no oracle: set ARKOS3_HOME or ARKOS2_HOME')
nframes, cols = ym

path, size = verify.export_song(args.song, args.player, verify.SIM_SONG)
data = open(path, 'rb').read()
mod = akl_reference if args.player == 'akl' else akm_reference
ref = mod.Player(data, verify.SIM_SONG)

mag = collections.Counter()
for f in range(nframes):
    us = list(ref.play())
    y = [cols[i][f] for i in range(14)]
    for ch in range(3):
        vy = y[8 + ch]
        tone = not (y[7] >> ch) & 1
        noise = not (y[7] >> (3 + ch)) & 1
        if not ((vy & 15 or vy & 16) and (tone or noise)):
            continue                                    # inaudible either way
        if not tone:
            continue
        py = y[2 * ch] | ((y[2 * ch + 1] & 15) << 8)
        pu = us[2 * ch] | ((us[2 * ch + 1] & 15) << 8)
        if py != pu:
            mag[abs(py - pu)] += 1

print('song:   %s (%s, %d bytes)' % (os.path.basename(args.song),
                                     args.player.upper(), size))
print('oracle: %s' % exe)
print('frames: %d' % nframes)
if not mag:
    print('no audible period differences at all')
else:
    print('audible period differences, by magnitude:')
    for k in sorted(mag):
        note = '   <- the documented +-1' if k == 1 else ''
        print('  |diff| = %-5d %6d frames%s' % (k, mag[k], note))
