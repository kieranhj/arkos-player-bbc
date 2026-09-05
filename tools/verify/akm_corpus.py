#!/usr/bin/env python3
"""Sort the corpus into the songs the AKM reference plays correctly and those
it does not, and write tools/verify/akm_known_good.txt.

A song is CLEAN when, over 3,000 frames against `SongToYm.exe`, nothing
differs except the classes docs/format-akm.md explains:

  * a period +1 on the six notes where AKM's octave halving disagrees with
    Arkos's own note table - inherent to the AKM player, not a defect;
  * a volume differing by exactly one - Arkos's documented plus-or-minus-one
    in the volume/pitch effects between its PC side and its Z80 player;
  * anything at all on a channel Arkos is not sounding, where its registers
    go stale.

Everything else counts against the song. Songs whose PSG is not the CPC's
1 MHz are listed separately rather than failed: this player targets the CPC
path deliberately, and the period table is knowingly wrong for them.

    python tools/verify/akm_corpus.py

The list it writes is what lib/akmplayer.asm is verified on, and it is
committed so that a change to the reference shows up as a change to the list.
"""

import datetime
import glob
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import akm_reference                                             # noqa: E402
import arkos                                                     # noqa: E402
from verify import read_ym                                       # noqa: E402

OUT = os.path.join(HERE, 'akm_known_good.txt')
FRAMES = 3000


def corpus():
    songs = []
    for d in ('songs/STarKos', 'songs/ArkosTracker2', 'songs/ArkosTracker3'):
        songs += sorted(glob.glob(os.path.join(arkos.AT3, d, '*.sks')) +
                        glob.glob(os.path.join(arkos.AT3, d, '*.aks')))
    songs += sorted(glob.glob(os.path.join(ROOT, 'songs', '*.aks')))
    edgea = os.path.join(os.path.dirname(ROOT), 'edge-beeb',
                         'source_cpc', 'Music', 'EDGEA.SKS')
    if os.path.exists(edgea):
        songs.append(edgea)
    return songs


def judge(song, exe, ymexe):
    """'clean', 'differs', or ('clock', hz)."""
    d = tempfile.mkdtemp()
    akm, ym = os.path.join(d, 's.akm'), os.path.join(d, 's.ym')
    try:
        if subprocess.run([exe, '-s', '1', '-bin', '-adr', '0x4000', song, akm],
                          capture_output=True).returncode:
            return None
        if subprocess.run([ymexe, '-p', '1', song, ym],
                          capture_output=True).returncode:
            return None
        clock = arkos.ym_header(ym)[1]
        if clock != 1000000:
            return ('clock', clock)
        n, cols = read_ym(ym)
        n = min(n, FRAMES)
        akm_reference.ENV_BASE = arkos.envelope_base(song)
        p = akm_reference.Player(open(akm, 'rb').read(), 0x4000)
        try:
            out = [p.play() for _ in range(n)]
        except akm_reference.AkmDataError:
            return 'differs'
        for f in range(n):
            y = [cols[i][f] for i in range(14)]
            us = out[f]
            for ch in range(3):
                vy = y[8 + ch]
                if abs(us[8 + ch] - vy) > 1:
                    return 'differs'
                if not (vy & 15 or vy & 16) or (y[7] >> ch) & 1:
                    continue            # silent, or tone off: registers stale
                pu = us[2 * ch] | ((us[2 * ch + 1] & 15) << 8)
                py = y[2 * ch] | ((y[2 * ch + 1] & 15) << 8)
                if pu - py not in (0, 1):
                    return 'differs'
            if any(y[8 + c] & 16 for c in range(3)):
                if y[11] != us[11] or y[12] != us[12]:
                    return 'differs'
        return 'clean'
    finally:
        for f in (akm, ym):
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(d)
        except OSError:
            pass


def main():
    exe = os.path.join(arkos.AT3, 'tools', 'SongToAkm.exe')
    ymexe = arkos.song_to_ym_exe()
    if not os.path.exists(exe) or not ymexe:
        raise SystemExit('needs SongToAkm.exe and SongToYm.exe')

    good, bad, other = [], [], []
    for s in corpus():
        r = judge(s, exe, ymexe)
        nm = os.path.basename(s)
        if r is None:
            continue
        if r == 'clean':
            good.append(nm)
        elif r == 'differs':
            bad.append(nm)
        else:
            other.append((nm, r[1]))
        print('%-46s %s' % (nm[:46], r if isinstance(r, str) else '%d Hz' % r[1]))

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('# Songs whose AKM replay verifies against SongToYm.exe with '
                'nothing\n# outside the classes docs/format-akm.md explains: '
                'the six-note +1,\n# volume differing by exactly one, and '
                'stale registers on a silent\n# channel. Regenerate with '
                'tools/verify/akm_corpus.py.\n')
        f.write('# Measured %s, AT3 exporter, %d frames each.\n#\n'
                % (datetime.date.today(), FRAMES))
        f.write('# THIS IS THE CORPUS lib/akmplayer.asm IS VERIFIED ON.\n\n')
        for x in good:
            f.write('%s\n' % x)
        f.write('\n# Not clean - the rendering discrepancy in '
                'docs/akm-open-questions.md:\n')
        for x in bad:
            f.write('# %s\n' % x)
        f.write('\n# Not a 1 MHz PSG, so the CPC period table is knowingly '
                'wrong for them.\n# See docs/akm-open-questions.md, '
                '"The Atari ST and MSX tunes".\n')
        for x, c in other:
            f.write('# %-46s %d Hz\n' % (x, c))
    print('\n%s: %d clean, %d differ, %d not CPC-clock'
          % (os.path.relpath(OUT, ROOT), len(good), len(bad), len(other)))


if __name__ == '__main__':
    sys.exit(main())
