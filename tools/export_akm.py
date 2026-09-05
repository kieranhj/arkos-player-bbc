#!/usr/bin/env python3
"""Export an Arkos song as "minimalist" (AKM) tracker data, for lib/akmplayer.asm.

    <song>.sks / .aks
      SongToAkm.exe -bin -adr <address>     ->  <out>.akm

AKM is an **Arkos Tracker 3** format, so unlike AKL this needs no Arkos
Tracker 2 install: one exe, shipped with the current tracker, and Targhan's
own documentation says AKM "may actually replace Lightweight". It is the
smallest Arkos format measured here - 3,654 bytes against AKL's 4,741 for
Edge Grinder's 349 seconds.

The address matters: AKM holds absolute pointers, so the binary must be
exported at the address it will be played from. Nothing checks this at run
time - a wrong address plays happily for thousands of frames before the
stream runs off the end of what it was given.

What this export loses, as AKM.md sets out: one PSG per subsong, no
hard-to-soft sounds, no events, speed changes only at the start of a
pattern, and hardware envelope shapes limited to ENV_BASE and ENV_BASE + 2 -
the same limitation AKL has, handled the same way. tools/arkos.py's
envelope_base() works out what a song needs.

Usage:
    python tools/export_akm.py songs/mysong.aks --addr 0x3000 -o build/mysong.akm
    python tools/export_akm.py songs/mysong.aks --check
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import arkos                                                     # noqa: E402

EXPORTER = os.path.join(arkos.AT3, 'tools', 'SongToAkm.exe')


def export(song, out, addr, subsong=1, exporter=EXPORTER, config=None):
    """Write the AKM binary. If `config` is given, the player config too."""
    if not os.path.exists(exporter):
        raise SystemExit(
            'SongToAkm.exe not found at %s\n'
            'AKM is an Arkos Tracker 3 format. Install AT3, or set\n'
            'ARKOS3_HOME / --exporter to where it lives.' % exporter)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    args = [exporter, '-s', str(subsong), '-bin', '-adr', hex(addr)]
    if config:
        args.append('--exportPlayerConfig')
    args += [song, out]
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stdout + r.stderr)
        raise SystemExit('SongToAkm failed (%d)' % r.returncode)
    return os.path.getsize(out)


def player_config(song, subsong=1, exporter=EXPORTER):
    """The PLY_CFG flags Arkos itself says this song needs, or None."""
    d = tempfile.mkdtemp()
    out = os.path.join(d, 'song.akm')
    cfg = os.path.join(d, 'song_playerconfig.asm')
    try:
        export(song, out, 0x4000, subsong, exporter, config=True)
        if not os.path.exists(cfg):
            return None
        return sorted(re.findall(
            r'PLY_CFG_(\w+)\s*=\s*1',
            open(cfg, encoding='utf-8', errors='replace').read()))
    except SystemExit:
        return None
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


def check(path, base, song=None, frames=6000):
    """Replay the export in the Python reference and report what it uses.

    RUN THIS BEFORE THE SIMULATOR, ALWAYS. AT2's AKL exporter is known to
    emit data whose pointers run outside the song, and fed that, a 6502
    replay does not fail - it SPINS, and a py65 harness sits in it
    indefinitely. Nothing says AKM's exporter has the same fault; nothing
    says it does not, and the cost of finding out the other way is an hour
    of silence. The Python reference raises in milliseconds.
    """
    sys.path.insert(0, os.path.join(HERE, 'verify'))
    import akm_reference                                          # noqa: E402

    d = open(path, 'rb').read()
    p = akm_reference.Player(d, base)
    fault = None
    try:
        for _ in range(frames):
            p.play()
    except akm_reference.AkmDataError as e:
        fault = str(e)

    print()
    print('subsong: speed %d, note table of %d entries at &%04X'
          % (p.speed, p.note_and_fx_flag, p.note_tbl))
    print('         primary/secondary instrument %d/%d, wait %d/%d'
          % (p.prim_inst, p.sec_inst, p.prim_wait, p.sec_wait))
    print('         effects %s'
          % ('present' if p.note_and_fx_flag == 12 else 'none in this song'))
    print('reached:  %s'
          % ', '.join('%s x%d' % kv for kv in sorted(p.stats.items())))
    if song:
        cfg = player_config(song)
        if cfg:
            print()
            print("Arkos's own player config for this song:")
            print('         %s' % ', '.join(cfg))

    if fault:
        print()
        print('*** THIS EXPORT IS NOT PLAYABLE ***')
        print('    %s' % fault)
        print('    Do NOT feed it to the 6502 harness: a wild pointer makes')
        print('    the replay spin rather than fail. See docs/format-akm.md.')
        return 1
    print()
    print('the export is self-consistent over %d frames (%d song loops)'
          % (frames, p.loops))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('song', help='an .sks or .aks Arkos song')
    ap.add_argument('--addr', default='0x3000',
                    help='the address the song will be PLAYED from (default 0x3000)')
    ap.add_argument('-o', '--out', help='output file (default: build/<song>.akm)')
    ap.add_argument('-s', '--subsong', type=int, default=1,
                    help='which subsong to export (>=1, default 1)')
    ap.add_argument('--exporter', default=EXPORTER,
                    help='path to SongToAkm.exe (Arkos Tracker 3)')
    ap.add_argument('--check', action='store_true',
                    help='replay the export in the Python reference and report '
                         'which player paths the song reaches')
    ap.add_argument('--limit', type=lambda s: int(s, 0), default=0,
                    help='fail if the data would run past this address')
    args = ap.parse_args()

    addr = int(args.addr, 0)
    out = args.out or os.path.join(
        ROOT, 'build', os.path.splitext(os.path.basename(args.song))[0] + '.akm')

    n = export(args.song, out, addr, args.subsong, args.exporter)
    print('%s: %d bytes, to be played from &%04X' % (out, n, addr))
    if args.limit:
        if addr + n > args.limit:
            raise SystemExit('the song runs past &%04X by %d bytes'
                             % (args.limit, addr + n - args.limit))
        print('room left below &%04X: %d bytes' % (args.limit, args.limit - addr - n))

    if args.check:
        return check(out, addr, args.song)


if __name__ == '__main__':
    sys.exit(main())
