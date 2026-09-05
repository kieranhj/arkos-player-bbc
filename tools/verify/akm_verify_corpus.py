#!/usr/bin/env python3
"""Run lib/akmplayer.asm against akm_reference.py over the whole known-good
corpus, and report every song that is not identical.

This is step 2's acceptance test. `verify.py --player akm` proves one song;
this proves the set in `akm_known_good.txt`, which is the corpus the player
claims to play - the 39 songs where the reference itself is clean against
Arkos's own replay. A song outside that list can still be run by hand; it
just cannot be used as evidence about the 6502, because the reference it
would be compared to is not clean on it.

    python tools/verify/akm_verify_corpus.py [--frames N]

Needs beebasm, py65, and an Arkos Tracker 3 install.
"""

import argparse
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import akm_corpus                                                # noqa: E402

KNOWN_GOOD = os.path.join(HERE, 'akm_known_good.txt')


def wanted():
    """The song names listed as clean, in akm_known_good.txt."""
    names = []
    for line in open(KNOWN_GOOD, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#'):
            names.append(line)
    return names


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--frames', type=int, default=2500,
                    help='frames per song (0 = the whole tune)')
    args = ap.parse_args()

    names = set(wanted())
    songs = [s for s in akm_corpus.corpus() if os.path.basename(s) in names]
    missing = names - set(os.path.basename(s) for s in songs)
    if missing:
        print('not found in the corpus: %s' % ', '.join(sorted(missing)))

    ok, bad, failed = [], [], []
    for s in songs:
        nm = os.path.basename(s)
        cmd = [sys.executable, os.path.join(HERE, 'verify.py'),
               '--player', 'akm', '--song', s]
        if args.frames:
            cmd += ['--frames', str(args.frames)]
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        out = r.stdout
        if 'IDENTICAL on every frame' in out:
            m = re.search(r'per 50 Hz field:\s+min (\d+)\s+mean (\d+)\s+'
                          r'p99 (\d+)\s+max (\d+)', out)
            cost = m.groups() if m else ('?',) * 4
            ok.append((nm, cost))
            print('%-46s identical   mean %s max %s' % (nm[:46], cost[1], cost[3]))
        elif '*** DIFFERS' in out:
            bad.append(nm)
            print('%-46s *** DIFFERS ***' % nm[:46])
            for line in out.splitlines():
                if 'first:' in line or '6502' in line or 'ref ' in line:
                    print('    %s' % line.strip())
        else:
            failed.append(nm)
            print('%-46s -- did not run' % nm[:46])

    print()
    print('%d songs: %d identical to the reference, %d differ, %d did not run'
          % (len(songs), len(ok), len(bad), len(failed)))
    if ok:
        means = [int(c[1]) for _, c in ok if c[1] != '?']
        maxes = [int(c[3]) for _, c in ok if c[3] != '?']
        print('cost over those songs, cycles per call @ 2 MHz: '
              'mean of means %d, worst frame %d' % (sum(means) // len(means),
                                                    max(maxes)))
    return 1 if (bad or failed) else 0


if __name__ == '__main__':
    sys.exit(main())
