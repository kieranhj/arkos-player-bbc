#!/usr/bin/env python3
"""Export an Arkos song as "lightweight" (AKL) tracker data, for lib/aklplayer.asm.

    <song>.sks / .aks
      SongToLightweight.exe -bin -adr <address>     ->  <out>.akl

THE FORMAT IS WITHDRAWN UPSTREAM. Arkos Tracker 3 ships no Lightweight
player and no SongToLightweight.exe, and AKM's own documentation says
"This player may actually replace Lightweight!". So this exporter needs an
**Arkos Tracker 2** install, permanently, and always will. AT3 cannot
produce the format. See docs/format-akl.md.

The address matters: AKL holds absolute pointers, so the binary must be
exported at the address it will be played from. Nothing checks this at run
time - a wrong address plays happily for thousands of frames before the
stream runs off the end of what it was given.

Two things this export loses, both documented in the AKL format spec:

  * Hardware envelope shapes: AKL encodes only 8 and 0xa. If your tune uses
    another, lib/aklplayer.asm's ENV_BASE has to compensate - it is 12 for
    EDGEA, which is 12 throughout. Set --env-base and the player to match,
    or use a format that carries the shape properly.
  * Arpeggio and pitch TABLES are exported, but the player's table paths
    have never been exercised by any tune tested so far. --check reports
    when a song strays into one.

Usage:
    python tools/export_akl.py songs/mysong.aks --addr 0x2000 -o build/mysong.akl
    python tools/export_akl.py songs/mysong.aks --check
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Arkos Tracker 2, because AT3 has removed the format. Override with
# --exporter or the ARKOS2_HOME environment variable.
AT2 = os.environ.get(
    'ARKOS2_HOME',
    os.path.join(os.path.expanduser('~'), 'OneDrive', 'Trackers',
                 'Arkos Tracker 2'))
EXPORTER = os.path.join(AT2, 'tools', 'SongToLightweight.exe')


def export(song, out, addr, exporter=EXPORTER):
    if not os.path.exists(exporter):
        raise SystemExit(
            'SongToLightweight.exe not found at %s\n'
            'AKL is an Arkos Tracker 2 format; AT3 has withdrawn it. Install\n'
            'AT2, or set ARKOS2_HOME / --exporter to where it lives.' % exporter)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    r = subprocess.run([exporter, '-bin', '-adr', hex(addr), song, out],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit('SongToLightweight failed (%d)' % r.returncode)
    return os.path.getsize(out)


def check(path, base, frames=6000):
    """Report what the song contains, and whether the export is self-consistent.

    The second half matters more than the first. AT2's exporter can emit a
    stream whose tracks reference an arpeggio or pitch table it did not
    write - see docs/format-akl.md. Nothing at run time detects that: the
    player reads two bytes of unrelated data as a pointer and walks off into
    the song. This replays the tune in the Python reference and says so.
    """
    sys.path.insert(0, os.path.join(HERE, 'verify'))
    import akl_reference                                        # noqa: E402

    d = open(path, 'rb').read()

    def w(a):
        o = a - base
        return d[o] | (d[o + 1] << 8)

    inst, arp, pit = w(base + 5), w(base + 7), w(base + 9)
    # The three index tables are laid out back to back, so each one's size is
    # bounded by the start of the next.
    n_arp, n_pit = (pit - arp) // 2, (inst - pit) // 2

    used = {'arp': -1, 'pit': -1}
    p = akl_reference.Player(d, base)
    o_arp, o_pit = akl_reference.Player.set_arp, akl_reference.Player.set_pit
    akl_reference.Player.set_arp = lambda s, t, n: (
        used.__setitem__('arp', max(used['arp'], n)), o_arp(s, t, n))[1]
    akl_reference.Player.set_pit = lambda s, t, n: (
        used.__setitem__('pit', max(used['pit'], n)), o_pit(s, t, n))[1]
    fault = None
    try:
        for _ in range(frames):
            p.play()
    except akl_reference.AklDataError as e:
        fault = str(e)
    finally:
        akl_reference.Player.set_arp, akl_reference.Player.set_pit = o_arp, o_pit

    print()
    print('arpeggio tables: %d (highest referenced: %s)'
          % (n_arp, used['arp'] if used['arp'] >= 0 else 'none'))
    print('pitch tables:    %d (highest referenced: %s)'
          % (n_pit, used['pit'] if used['pit'] >= 0 else 'none'))
    print('features:        %s'
          % ', '.join('%s x%d' % kv for kv in sorted(p.stats.items())))

    bad = []
    if used['arp'] >= n_arp:
        bad.append('arpeggio %d, but only %d were exported' % (used['arp'], n_arp))
    if used['pit'] >= n_pit:
        bad.append('pitch %d, but only %d were exported' % (used['pit'], n_pit))
    if bad or fault:
        print()
        print('*** THIS EXPORT IS NOT PLAYABLE ***')
        for b in bad:
            print('    the tracks reference %s' % b)
        if fault:
            print('    %s' % fault)
        print('    This is an ARKOS TRACKER 2 EXPORTER fault, not a player one:')
        print("    Arkos's own Z80 player reads the same out-of-range entry.")
        print('    Use a different format (AKY, via Arkos Tracker 3) for this song.')
        return 1
    print()
    print('the export is self-consistent over %d frames' % frames)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('song', help='an .sks or .aks Arkos song')
    ap.add_argument('--addr', default='0x2000',
                    help='the address the song will be PLAYED from (default 0x2000)')
    ap.add_argument('-o', '--out', help='output file (default: build/<song>.akl)')
    ap.add_argument('--exporter', default=EXPORTER,
                    help='path to SongToLightweight.exe (Arkos Tracker 2)')
    ap.add_argument('--check', action='store_true',
                    help='report which player features the song uses')
    ap.add_argument('--limit', type=lambda s: int(s, 0), default=0,
                    help='fail if the data would run past this address')
    args = ap.parse_args()

    addr = int(args.addr, 0)
    out = args.out or os.path.join(
        ROOT, 'build', os.path.splitext(os.path.basename(args.song))[0] + '.akl')

    n = export(args.song, out, addr, args.exporter)
    print('%s: %d bytes, to be played from &%04X' % (out, n, addr))
    if args.limit:
        if addr + n > args.limit:
            raise SystemExit('the song runs past &%04X by %d bytes'
                             % (args.limit, addr + n - args.limit))
        print('room left below &%04X: %d bytes' % (args.limit, args.limit - addr - n))

    if args.check:
        return check(out, addr)


if __name__ == '__main__':
    sys.exit(main())
