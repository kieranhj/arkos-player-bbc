#!/usr/bin/env python3
"""Find a jsbeeb SN76489 capture inside a simulated .snf stream.

The last check in the chain, and the only one that can catch a wiring,
paging or interrupt bug: everything else runs the player in a simulator that
cannot get those wrong. Capture the bytes the real machine wrote with
jsbeeb's start_sound_capture / stop_sound_capture, paste them in, and this
says whether the emulator's chip saw exactly what the simulation says it
should - and where in the tune it was.

    python tools/verify/find_capture.py <capture.txt> <simulated.snf>

The capture file is jsbeeb's output pasted verbatim; every `0xNN` on a line
is taken in order and everything else ignored.

A match at ONE offset is the proof. Several offsets is not a failure - a
tune repeats, and a sustained passage writes the same bytes every field -
but it means the capture was not distinctive enough to pin the position, so
capture across a change of note.
"""

import re
import struct
import sys


def read_snf(path):
    d = open(path, 'rb').read()
    assert d[:4] == b'SNF1', 'not an .snf'
    n, rate, clock, fb, w = struct.unpack('<IIIHH', d[4:20])
    o = 20
    frames = []
    for _ in range(n):
        ln = d[o]
        o += 1
        frames.append(list(d[o:o + ln]))
        o += ln
    return frames


def read_capture(path):
    text = open(path, encoding='utf-8', errors='replace').read()
    return [int(x, 16) for x in re.findall(r'0x([0-9a-fA-F]{2})', text)]


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    cap = read_capture(sys.argv[1])
    frames = read_snf(sys.argv[2])
    flat = [b for f in frames for b in f]

    # Where each frame starts in the flattened stream, so a hit can be
    # reported as a frame number rather than a byte offset.
    starts, at = [], 0
    for f in frames:
        starts.append(at)
        at += len(f)

    print('capture:   %d writes' % len(cap))
    print('simulated: %d frames, %d writes' % (len(frames), len(flat)))

    hits = [i for i in range(len(flat) - len(cap) + 1)
            if flat[i:i + len(cap)] == cap]
    print()
    if not hits:
        print('*** NOT FOUND ***')
        print('The bytes the real machine wrote do not appear in the')
        print('simulation. That is a wiring, paging or interrupt fault -')
        print('everything upstream of this runs in a simulator that cannot')
        print('get those wrong.')
        return 1

    for h in hits:
        frame = max(i for i, s in enumerate(starts) if s <= h)
        print('found at byte %d, inside frame %d (%.1f s into the tune)'
              % (h, frame, frame / 50.0))
    if len(hits) == 1:
        print('\nExactly one place. The machine wrote what the simulation says.')
    else:
        print('\n%d places - the tune repeats here, so the capture does not pin'
              % len(hits))
        print('the position. Every one is a byte-for-byte match; capture across')
        print('a change of note to narrow it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
