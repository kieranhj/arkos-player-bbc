#!/usr/bin/env python3
"""Which AKM player paths does each song actually reach?

"A path nothing has ever called is not a tested path." AKL shipped with five
of its seven effects never once executed, because the tune it was written for
uses none of them. This is the tool that stops AKM repeating it.

SongToAkm can emit a per-song `_playerconfig.asm` naming exactly which
features a tune uses - Arkos's own answer, not ours - so this exports every
song in the corpus and collects those flags. It reports:

  * per song: size, and the player paths it reaches;
  * the corpus leaders by coverage, which is how the demo tune gets chosen;
  * what NOTHING in the corpus reaches, which is what the docs must admit to.

    python tools/survey_akm.py [extra songs...]

Writes build/akm-coverage.md. Nothing is committed: the Arkos songs stay in
the Arkos install and EDGEA stays in edge-beeb.
"""
import glob
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import arkos                                                     # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AT3 = arkos.AT3

# Every PLY_CFG flag lib/akmplayer.asm has a branch for, in the order the
# player meets them. A flag absent from a song's config is a path that song
# never executes.
PATHS = [
    ('UseTranspositions',            'linker: transposition'),
    ('UseSpeedTracks',               'linker: speed change'),
    ('UseInstrumentLoopTo',          'instrument: loop-to cell'),
    ('NoSoftNoHard',                 'instrument: no soft, no hard'),
    ('NoSoftNoHard_Noise',           'instrument: NSNH + noise'),
    ('SoftOnly',                     'instrument: software'),
    ('SoftOnly_Noise',               'instrument: software + noise'),
    ('SoftOnly_SoftwareArpeggio',    'instrument: software + arpeggio'),
    ('SoftOnly_SoftwarePitch',       'instrument: software + pitch'),
    ('UseHardwareSounds',            'instrument: hardware at all (R11-R13)'),
    ('SoftToHard',                   'instrument: software to hardware'),
    ('SoftToHard_SoftwareArpeggio',  'instrument: S2H + arpeggio'),
    ('SoftToHard_SoftwarePitch',     'instrument: S2H + pitch'),
    ('SoftAndHard',                  'instrument: software and hardware'),
    ('SoftAndHard_SoftwareArpeggio', 'instrument: S&H + arpeggio'),
    ('SoftAndHard_SoftwarePitch',    'instrument: S&H + pitch'),
    ('UseEffects',                   'effects at all'),
    ('UseEffect_Reset',              'effect 0: reset with volume'),
    ('UseEffect_SetVolume',          'effect 1: set volume'),
    ('UseEffect_PitchUp',            'effect 2: pitch up'),
    ('UseEffect_PitchDown',          'effect 2: pitch down'),
    ('UseEffect_ArpeggioTable',      'effect 3: arpeggio table'),
    ('UseEffect_PitchTable',         'effect 4: pitch table'),
    ('UseEffect_ForceInstrumentSpeed', 'effect 5: force instrument speed'),
    ('UseEffect_ForceArpeggioSpeed', 'effect 6: force arpeggio speed'),
    ('UseEffect_ForcePitchTableSpeed', 'effect 7: force pitch speed'),
]
NAMES = [p[0] for p in PATHS]


def akm_config(song):
    """(size, set of PLY_CFG flags) for this song, or None if it will not export."""
    exe = os.path.join(AT3, 'tools', 'SongToAkm.exe')
    if not os.path.exists(exe):
        raise SystemExit('SongToAkm.exe not found at %s' % exe)
    d = tempfile.mkdtemp()
    out = os.path.join(d, 'song.akm')
    cfg = os.path.join(d, 'song_playerconfig.asm')
    try:
        r = subprocess.run([exe, '-s', '1', '-bin', '-adr', '0x4000',
                            '--exportPlayerConfig', song, out],
                           capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            return None
        flags = set()
        if os.path.exists(cfg):
            flags = set(re.findall(r'PLY_CFG_(\w+)\s*=\s*1',
                                   open(cfg, encoding='utf-8',
                                        errors='replace').read()))
        return os.path.getsize(out), flags
    finally:
        for f in (out, cfg):
            try:
                os.remove(f)
            except OSError:
                pass
        try:
            os.rmdir(d)
        except OSError:
            pass


def corpus():
    songs = []
    for d in ('songs/STarKos', 'songs/ArkosTracker2', 'songs/ArkosTracker3'):
        songs += sorted(glob.glob(os.path.join(AT3, d, '*.sks')) +
                        glob.glob(os.path.join(AT3, d, '*.aks')))
    songs += sorted(glob.glob(os.path.join(ROOT, 'songs', '*.aks')))
    edgea = os.path.join(os.path.dirname(ROOT), 'edge-beeb',
                         'source_cpc', 'Music', 'EDGEA.SKS')
    if os.path.exists(edgea):
        songs.append(edgea)
    songs += [a for a in sys.argv[1:] if os.path.exists(a)]
    return songs


def main():
    rows = []
    for s in corpus():
        got = akm_config(s)
        if not got:
            print('%-52s EXPORT FAILED' % os.path.basename(s)[:52])
            continue
        size, flags = got
        reached = [n for n in NAMES if n in flags]
        rows.append((os.path.basename(s), s, size, flags, len(reached)))
        print('%-52s %6d bytes  %2d/%d paths'
              % (os.path.basename(s)[:52], size, len(reached), len(NAMES)))

    if not rows:
        raise SystemExit('no songs exported')

    rows.sort(key=lambda r: (-r[4], r[2]))
    # Only the flags the player actually branches on. A config carries others
    # (ConfigurationIsPresent, SoftAndHard_ForcedHardwarePeriod - which in AKM
    # is not a choice, the format having no other kind of SoftAndHard) and
    # counting those would overstate the coverage.
    union = set().union(*[r[3] & set(NAMES) for r in rows])
    missing = [n for n in NAMES if n not in union]

    print()
    print('best coverage:')
    for name, _, size, flags, n in rows[:8]:
        print('  %2d/%d  %6d bytes  %s' % (n, len(NAMES), size, name))

    # The greedy cover: the smallest set of tunes that between them reach
    # everything the corpus can reach. This is the test set, not just the
    # demo tune.
    need, cover = set(union), []
    while need:
        best = max(rows, key=lambda r: len(r[3] & need))
        if not (best[3] & need):
            break
        cover.append((best[0], sorted(best[3] & need)))
        need -= best[3]
    print()
    print('a set that reaches everything the corpus reaches:')
    for name, adds in cover:
        print('  %-46s adds %s' % (name[:46], ', '.join(adds)))

    print()
    print('NOTHING in the corpus reaches (%d paths):' % len(missing))
    for n in missing:
        print('  %s - %s' % (n, dict(PATHS)[n]))

    os.makedirs(os.path.join(ROOT, 'build'), exist_ok=True)
    out = os.path.join(ROOT, 'build', 'akm-coverage.md')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('# Which AKM player paths each song reaches\n\n')
        f.write('Generated by `tools/survey_akm.py` from `SongToAkm '
                '--exportPlayerConfig`, which is Arkos\'s own answer to the\n'
                'question, not ours. Not committed: the songs live in the '
                'Arkos install.\n\n')
        f.write('| song | AKM bytes | paths reached |\n|---|--:|--:|\n')
        for name, _, size, _, n in rows:
            f.write('| %s | %d | %d/%d |\n' % (name, size, n, len(NAMES)))
        f.write('\n## A test set that reaches everything the corpus reaches\n\n')
        for name, adds in cover:
            f.write('- **%s** adds %s\n' % (name, ', '.join(adds)))
        f.write('\n## Reached by nothing in the corpus\n\n')
        if missing:
            for n in missing:
                f.write('- `PLY_CFG_%s` - %s\n' % (n, dict(PATHS)[n]))
        else:
            f.write('Nothing: every path is exercised by some song.\n')
    print('\n%s written, %d songs' % (out, len(rows)))


if __name__ == '__main__':
    sys.exit(main())
