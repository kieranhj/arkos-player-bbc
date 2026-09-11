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
import re
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


def find(*cands):
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


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


def envelope_base(song, default=8):
    """The ENV_BASE lib/aklplayer.asm needs for this song.

    AKL stores ONE BIT of envelope shape, meaning ENV_BASE or ENV_BASE + 2,
    and the format defines those as 8 and 10 - so 8 suits any tune that
    actually uses 8 or 10. A tune whose real envelope AKL cannot encode gets
    a substitute on export, and the player has to shift the pair back: Edge
    Grinder's EDGEA is envelope 12 throughout and needs 12.

    AKG can carry the true shape, and SongToAkg's SOURCE export writes it
    into a comment, so that is where this reads it from. Returns `default`
    if AKG cannot be run - a wrong guess shows up as `env shape` mismatches
    in tools/verify/verify.py rather than silently.
    """
    exe = find(os.path.join(AT3, 'tools', 'SongToAkg.exe'),
               os.path.join(AT2, 'tools', 'SongToAkg.exe'))
    if not exe:
        return default
    fd, tmp = tempfile.mkstemp(suffix='.asm')
    os.close(fd)
    try:
        # AT3's exporter takes -s; AT2's does not. Try it, then without.
        r = subprocess.run([exe, '-s', '1', song, tmp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            r = subprocess.run([exe, song, tmp], capture_output=True, text=True)
        if r.returncode != 0:
            return default
        text = open(tmp, encoding='utf-8', errors='replace').read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    shapes = set(int(n) for n in re.findall(r'Envelope:\s*(\d+)', text))
    if not shapes:
        return default
    base = min(shapes) & ~1                 # the pair is (base, base + 2)
    if not shapes <= {base, base + 2}:
        sys.stderr.write(
            'warning: %s uses envelope shapes %s, which are not one AKL '
            'pair; using %d\n' % (os.path.basename(song), sorted(shapes), base))
    return base



def initial_transpositions(song, default=(0, 0, 0)):
    """The per-channel transposition at position 0, from Arkos's own export.

    AKL's linker encodes a transposition only when it CHANGES, and the player
    starts at zero - so a song whose first position is transposed depends on
    the exporter writing it there. AT2's SongToLightweight does not always:
    Edge Grinder's WON4 needs (0, -3, -7) at position 0 and the AKL export
    carries no transposition at all, which is 216 frames of wrong notes.
    See docs/format-akl.md, "WON4 plays wrong notes".

    `SongToAkm.exe` without -bin annotates every byte it writes, and its
    linker names each transposition and the channel it belongs to, so it is
    the oracle for what position 0 should be. Returns `default` if AKM cannot
    be run, since no check is better than a wrong one.
    """
    exe = find(os.path.join(AT3, 'tools', 'SongToAkm.exe'),
               os.path.join(AT2, 'tools', 'SongToAkm.exe'))
    if not exe:
        return default
    fd, tmp = tempfile.mkstemp(suffix='.asm')
    os.close(fd)
    try:
        r = subprocess.run([exe, song, tmp], capture_output=True, text=True)
        if r.returncode != 0:
            return default
        text = open(tmp, encoding='utf-8', errors='replace').read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    # Just the first position: a later one may transpose without position 0 doing so.
    start = text.find('; Position 0')
    if start < 0:
        return default
    end = text.find('; Position 1', start)
    block = text[start:end if end > 0 else len(text)]
    tr = [0, 0, 0]
    for val, ch in re.findall(
            r'db\s+(-?\d+)\s*;\s*New transposition on channel (\d)', block):
        i = int(ch) - 1
        if 0 <= i < 3:
            tr[i] = int(val)
    return tuple(tr)


def mid_pattern_speeds(song, subsong=0):
    """Speed changes that fall INSIDE a pattern: [(position, row, speed)].

    AKL and AKM encode a speed only at the start of a pattern (AKM.md: "Only
    speed change at the start of a pattern are encoded"; the AKL spec says
    the same). Every other cell of the speed track is dropped on export, and
    the pattern plays at its first speed throughout. h0ffman's "His Masters
    Rasters" alternates 5/4 on every row; as AKM it played about 11% slow,
    the 6502 byte-identical to akm_reference.py all the while, and only the
    YM oracle - thousands of period mismatches - or the composer could tell.
    AKY is a register stream and keeps the timing.

    Reads both .aks XML layouts (each a zip). AT2's is namespaced and each
    <pattern> of a subsong IS a position, with its own height and speed
    track number. AT3's 3.0 has no namespace: <position> gives a height and a
    patternIndex, the pattern names its speed track in <speedTrackIndex>, and
    a song with no speed changes has no <speedTracks> at all. Returns None for
    anything it cannot read (.sks, .128), since no answer is better than a
    wrong one.
    """
    import xml.etree.ElementTree as ET
    import zipfile
    try:
        with zipfile.ZipFile(song) as z:
            root = ET.fromstring(z.read(z.namelist()[0]))
    except (zipfile.BadZipFile, ET.ParseError, OSError, IndexError):
        return None
    num = lambda e, tag, d=0: int(e.findtext(tag, str(d)))
    if root.tag == 'song':                                      # AT3, 3.0
        subs = root.findall('subsongs/subsong')
        if subsong >= len(subs):
            return None
        ss = subs[subsong]
        tracks = {num(st, 'index'): [(num(c, 'index'), num(c, 'value'))
                                     for c in st.findall('cell')]
                  for st in ss.findall('speedTracks/speedTrack')}
        pats = [num(p, 'speedTrackIndex/trackIndex')
                for p in ss.findall('patterns/pattern')]
        poss = ss.findall('positions/position')
        end = num(ss, 'endPosition', len(poss) - 1)
        rows = [(num(p, 'height', 64), pats[num(p, 'patternIndex')])
                for p in poss[:end + 1]]
    else:                                                       # AT2
        a = '{http://www.julien-nevo.com/ArkosTrackerSong}'
        subs = root.findall('%ssubsongs/%ssubsong' % (a, a))
        if subsong >= len(subs):
            return None
        ss = subs[subsong]
        tracks = {num(st, a + 'number'): [(num(c, a + 'index'), num(c, a + 'value'))
                                          for c in st.findall(a + 'speedCell')]
                  for st in ss.findall('%sspeedTracks/%sspeedTrack' % (a, a))}
        pats = ss.findall('%spatterns/%spattern' % (a, a))
        end = num(ss, a + 'endIndex', len(pats) - 1)
        rows = [(num(p, a + 'height', 64), num(p, a + 'speedTrackNumber'))
                for p in pats[:end + 1]]
    found = []
    for pos, (h, n) in enumerate(rows):
        found += [(pos, row, v) for row, v in tracks.get(n, ()) if 0 < row < h]
    return found


def warn_mid_pattern_speeds(song, player):
    """Say so if `player` is AKL or AKM and the song needs AKY's timing."""
    if player not in ('akl', 'akm'):
        return
    found = mid_pattern_speeds(song)
    if found:
        pos, row, v = found[0]
        sys.stderr.write(
            'warning: %s changes speed inside a pattern %d times (first: '
            'position %d, row %d, speed %d), which %s cannot encode - it will '
            'play at the wrong tempo. Use --player aky.\n'
            % (os.path.basename(song), len(found), pos, row, v, player.upper()))


if __name__ == '__main__':
    for s in sys.argv[1:]:
        mps = mid_pattern_speeds(s)
        print('%-46s %d Hz, ENV_BASE %d, transpositions %s, mid-pattern speeds %s'
              % (os.path.basename(s), replay_rate(s), envelope_base(s),
                 list(initial_transpositions(s)),
                 '?' if mps is None else len(mps)))
