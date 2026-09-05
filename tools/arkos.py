#!/usr/bin/env python3
"""Facts about an Arkos song that are NOT in its exported data.

The one that matters is the replay rate. A song is authored to be played a
fixed number of times a second and **that number is not carried in the AKL or
AKY export** - the player just replays as often as you call it. Call it at
the wrong rate and the tune plays at the wrong speed, in tune, with nothing
to indicate anything is wrong.

Most Arkos songs are 50 Hz. Not all: Targhan's "Dead On Time - Ingame" is
25 Hz, and playing it every field made it exactly twice too fast (KC heard
it; Arkos renders the tune as 149.0 s and 3,726 player calls at 50 Hz is
74.5 s).

SongToYm.exe writes the rate into its YM header, so that is where this
reads it from.
"""

import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BEEB = os.path.dirname(os.path.dirname(ROOT))
HOME = os.path.expanduser('~')

AT3 = os.environ.get('ARKOS3_HOME',
                     os.path.join(HOME, 'OneDrive', 'Trackers', 'ArkosTracker3'))
AT2 = os.environ.get('ARKOS2_HOME',
                     os.path.join(HOME, 'OneDrive', 'Trackers', 'Arkos Tracker 2'))


def song_to_ym_exe():
    for c in (os.path.join(AT3, 'tools', 'SongToYm.exe'),
              os.path.join(AT2, 'tools', 'SongToYm.exe'),
              os.path.join(BEEB, 'Repos', 'nova-invite', 'bin', 'SongToYm.exe')):
        if os.path.exists(c):
            return c
    return None


def ym_header(path):
    """(frames, psg_clock_hz, replay_rate_hz) from a YM5/YM6 file."""
    d = open(path, 'rb').read()
    if d[:4] not in (b'YM5!', b'YM6!'):
        raise ValueError('%s is not a YM5/YM6 file' % path)
    frames, = struct.unpack('>I', d[12:16])
    clock, = struct.unpack('>I', d[22:26])
    rate, = struct.unpack('>H', d[26:28])
    return frames, clock, rate


def replay_rate(song, default=50):
    """How many times a second this song's player must be called.

    Returns `default` if no SongToYm.exe can be found, because a build
    should not fail over this - but it will then be wrong for the songs
    that are not 50 Hz, so callers should say which they used.
    """
    exe = song_to_ym_exe()
    if not exe:
        return default
    fd, tmp = tempfile.mkstemp(suffix='.ym')
    os.close(fd)
    try:
        r = subprocess.run([exe, '-p', '1', song, tmp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return default
        return ym_header(tmp)[2] or default
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


if __name__ == '__main__':
    for s in sys.argv[1:]:
        print('%-46s %d Hz' % (os.path.basename(s), replay_rate(s)))
