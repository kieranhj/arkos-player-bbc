#!/usr/bin/env python3
"""Build the demo discs: one per player, each with a song and a !BOOT.

    python example/build.py                 # both, with the default songs
    python example/build.py --player aky --song path/to/song.aks

Run from the REPO ROOT. Produces build/ARKOS-AKL.SSD and build/ARKOS-AKY.SSD;
boot either with SHIFT-BREAK.

Each disc is one file: the code, then the song assembled at &3000. The song
has to be exported at the address it is played from, which is why this
script exists at all rather than a one-line beebasm invocation.
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(HERE, 'build')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import arkos                                                     # noqa: E402

SONG_ADDR = 0x3000

HOME = os.path.expanduser('~')
AT3 = os.environ.get('ARKOS3_HOME',
                     os.path.join(HOME, 'OneDrive', 'Trackers', 'ArkosTracker3'))
BEEB = os.path.dirname(os.path.dirname(ROOT))

# The defaults. AKL gets a Targhan song because Arkos Tracker 2's AKL
# exporter cannot correctly export the Rhino tune - see docs/format-akl.md.
DEFAULTS = {
    'akl': (os.path.join(AT3, 'songs', 'STarKos',
                         'Targhan - Dead On Time - Ingame.sks'),
            'Targhan - Dead On Time (Ingame)'),
    'aky': (os.path.join(ROOT, 'songs', 'Acid_demo_21.aks'),
            'Rhino - Acid Demo'),
    # AKM's tune is chosen by MEASUREMENT, not preference: of the 75 songs
    # tools/survey_akm.py sweeps, Targhan's Crtc reaches 21 of the player's
    # 26 paths - including the pitch table and two of the force-speed
    # effects, three paths AKL has still never executed.
    'akm': (os.path.join(AT3, 'songs', 'ArkosTracker2', 'Targhan - Crtc.aks'),
            'Targhan - Crtc'),
}

# Two more AKL discs, built with --extra, both of them test cases rather than
# demos. EDGEA is the tune the library was built for and the only one here
# that uses the hardware envelope; Orion Prime Level 4 is the hardest bass of
# the 75 surveyed - 69% of its audible channel-frames are below the chip's
# floor and 54% of its bass calls want two voices at once.
EXTRA = {
    'edgea': (os.path.join(BEEB, 'Repos', 'edge-beeb', 'source_cpc', 'Music',
                           'EDGEA.SKS'),
              'Tom&Jerry - Edge Grinder'),
    'orion': (os.path.join(AT3, 'songs', 'STarKos',
                           'Targhan - Orion Prime - Level 4 - Theme 1.sks'),
              'Targhan - Orion Prime L4'),
}


def beebasm():
    for c in (os.path.join(ROOT, 'bin', 'beebasm.exe'),
              os.path.join(BEEB, 'Bin', 'beebasm.exe')):
        if os.path.exists(c):
            return c
    return 'beebasm'


def export(song, player, out):
    if player == 'akl':
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'export_akl.py'),
                        song, '--addr', hex(SONG_ADDR), '-o', out],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    elif player == 'akm':
        subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'export_akm.py'),
                        song, '--addr', hex(SONG_ADDR), '-o', out],
                       cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    else:
        exe = os.path.join(AT3, 'tools', 'SongToAky.exe')
        r = subprocess.run([exe, '-s', '1', '-bin', '-adr', hex(SONG_ADDR), song, out],
                           capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout + r.stderr)
            raise SystemExit('SongToAky failed')


def aky_psgs(path):
    """Three channels make a PSG. The player handles the rest itself."""
    return (open(path, 'rb').read()[1] + 2) // 3


def build(player, song, title, disc=None):
    os.makedirs(BUILD, exist_ok=True)
    # AKL and AKM keep only a pattern's first speed; a song that changes speed
    # mid-pattern plays at the wrong tempo with nothing else to show for it.
    arkos.warn_mid_pattern_speeds(song, player)
    binary = os.path.join(BUILD, 'song.bin')
    export(song, player, binary)
    if player == 'aky':
        n = aky_psgs(binary)
        if n > 1:
            print('  %d PSGs: playing the first, ignoring %d more channels'
                  % (n, 3 * (n - 1)))

    # A song is authored for a fixed replay rate and the exported data does
    # not carry it. The demo runs off VSync at 50 Hz, so it needs a divider.
    rate = arkos.replay_rate(song)
    div = max(1, int(round(50.0 / rate)))
    if div != 1:
        print('  %d Hz song: calling the player every %d fields' % (rate, div))

    # The envelope pair is a property of the SONG, not the player, and AKM
    # has AKL's limitation unchanged.
    env_base = arkos.envelope_base(song) if player in ('akl', 'akm') else 8
    if env_base != 8:
        print('  envelope %d: ENV_BASE %d' % (env_base, env_base))

    # AKL's linker encodes a transposition only when it CHANGES and the
    # player starts at zero, so a song whose FIRST position is transposed
    # depends on AT2's exporter writing it there - and it does not always.
    # WON4 needs (0, -3, -7) and gets nothing: 216 frames in the wrong key.
    # export_akl.py --check refuses such an export; this sets it instead.
    transp = (0, 0, 0)
    if player == 'akl':
        transp = arkos.initial_transpositions(song)
        if transp != (0, 0, 0):
            print('  position 0 transposes %s: setting t_transp after akl_init'
                  % list(transp))

    with open(os.path.join(BUILD, 'config.asm'), 'w') as f:
        f.write('\\ Generated by example/build.py - do not edit.\n')
        f.write('PLAYER_AKY = %d\n' % (player == 'aky'))
        f.write('PLAYER_AKM = %d\n' % (player == 'akm'))
        f.write('REPLAY_DIV = %d\n' % div)
        f.write('ENV_BASE = %d\n' % env_base)
        # The demo's B key cycles the three bass voices by ear, so it
        # needs all of them: -1 is the runtime choice. A host that has
        # picked one wants 0, 1 or 2 and the bytes back - see
        # lib/ay2sn.asm's header and docs/performance.md.
        f.write('BASS_MODE = -1\n')
        f.write('SONG_TRANSP0 = %d\n' % transp[0])
        f.write('SONG_TRANSP1 = %d\n' % transp[1])
        f.write('SONG_TRANSP2 = %d\n' % transp[2])
        f.write('SONG_TITLE = "%s"\n' % title.replace('"', "'"))

    name = {'aky': 'AKYDEMO', 'akm': 'AKMDEMO'}.get(player, 'AKLDEMO')
    with open(os.path.join(BUILD, 'boot.txt'), 'w') as f:
        f.write('*BASIC\r*RUN %s\r' % name)

    ssd = os.path.join(ROOT, 'build',
                       'ARKOS-%s.SSD' % (disc or player).upper())
    os.makedirs(os.path.dirname(ssd), exist_ok=True)
    r = subprocess.run([beebasm(), '-i', 'example/demo.asm', '-do', ssd,
                        '-boot', name, '-title', 'ARKOS', '-opt', '3'],
                       cwd=ROOT, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit('beebasm failed for %s' % player)
    print('%s: %s  (%s)' % (ssd, os.path.basename(song), title))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--player', choices=('akl', 'aky', 'akm'))
    ap.add_argument('--song')
    ap.add_argument('--title', default=None)
    ap.add_argument('--disc', default=None,
                    help='name the image build/ARKOS-<DISC>.SSD instead of '
                         'ARKOS-<PLAYER>.SSD, so a one-off song disc does not '
                         'overwrite the demo')
    ap.add_argument('--extra', action='store_true',
                    help='also build the two extra AKL discs, EDGEA and ORION')
    args = ap.parse_args()

    if args.extra:
        for disc, (song, title) in EXTRA.items():
            if not os.path.exists(song):
                print('skipping %s: %s not found' % (disc, song))
                continue
            build('akl', song, title, disc)
        return

    players = [args.player] if args.player else ['akl', 'aky', 'akm']
    for p in players:
        song, title = DEFAULTS[p]
        if args.song:
            song = args.song
            title = args.title or os.path.splitext(os.path.basename(song))[0]
        if not os.path.exists(song):
            print('skipping %s: %s not found' % (p, song))
            continue
        build(p, song, title, args.disc)


if __name__ == '__main__':
    sys.exit(main())
