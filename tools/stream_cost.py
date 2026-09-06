#!/usr/bin/env python3
"""What the AY->SN conversion costs a compressor, register stream by register stream.

Written to answer one question: why is a FAP export of Rhino's Acid Demo 21
5,600 bytes when the VGC of the same tune is 7,460? Both are per-register
stream compressors, so the answer had to be in either the INPUT or the CODER,
and this tool measures the input half.

It reads the .ym that SongToFap crunches and the .vgm that vgmpacker crunches -
the same tune, after ym2sn.py has done the AY->SN conversion offline - and
prints, for every byte stream each of them sees, how often it changes and what
one common coder (zlib -9, a yardstick, NOT something an 8-bit decoder can
reach) makes of it.

What it caught: the SN76489 log of a tune costs 1.76x to 2.06x the AY log of
the same tune, on all four demo tunes, before any compressor is chosen. Two
causes are visible in the per-stream rows. The AY's 12-bit period splits 8+4,
so the coarse byte is nearly static - r3 changes on 3.3% of Acid Demo's frames;
the SN's 10-bit period splits 4+6, so both bytes are active - 40.1% and 43.8%.
And the AY's volume streams are more REPETITIVE even where they change more
often (r8 changes on 43.3% of frames and zlibs to 267 bytes; SN vol0 changes on
19.3% and zlibs to 445), because envelope simulation and requantising 16 AY
levels onto a 4-bit log scale break up the patterns.

That is the whole of FAP's size advantage over VGC, and it is not FAP's coder:
VGC's RLE + LZ4 + Huffman lands within 1.2-1.4x of the zlib yardstick where
FAP's plain LZSS lands within 2.0-2.2x.

The controlled version of the same experiment is FAP against .vgi, which is the
same design as FAP - eleven columns, byte-aligned LZSS, 256-byte ring window,
8-bit offsets - on SN registers instead of AY ones. With the coder held
constant, VGI's files are 1.48x to 1.99x FAP's, which is this tool's ratio and
nothing else. See docs/porting.md.

    python tools/stream_cost.py build/fmt/Rhino_Acid_Demo_21.ym \
                               build/fmt/Rhino_Acid_Demo_21.vgm

The inputs are the ones tools/compare_formats.py leaves in build/fmt.
"""
import struct
import sys
import zlib


def read_ym(path):
    """(frames, psg clock, replay rate, 14 register streams) from a YM5/YM6."""
    d = open(path, 'rb').read()
    if d[:4] not in (b'YM5!', b'YM6!'):
        raise ValueError('%s is not a YM5/YM6 file' % path)
    off = 12                                        # id + 'LeOnArD!'
    frames, attrs, digidrums = struct.unpack('>IIH', d[off:off + 10])
    off += 10
    clock, rate, _loop, skip = struct.unpack('>IHIH', d[off:off + 12])
    off += 12 + skip
    for _ in range(3):                              # song, author, comment
        off = d.index(b'\0', off) + 1
    if attrs & 1:                                   # interleaved
        return frames, clock, rate, \
            [d[off + r * frames: off + (r + 1) * frames] for r in range(14)]
    regs = [bytearray() for _ in range(16)]
    for f in range(frames):
        for r in range(16):
            regs[r].append(d[off + f * 16 + r])
    return frames, clock, rate, [bytes(r) for r in regs[:14]]


def read_vgm_sn(path):
    """Per-frame (tone[4], volume[4]) from a VGM of SN76489 writes."""
    d = open(path, 'rb').read()
    if d[:4] != b'Vgm ':
        raise ValueError('%s is not a VGM file' % path)
    off = struct.unpack('<I', d[0x34:0x38])[0]
    off = 0x34 + off if off else 0x40
    tone, vol, latch, kind = [0] * 4, [15] * 4, 0, 0
    frames = []
    i = off
    while i < len(d):
        c = d[i]
        if c == 0x50:                               # SN76489 write
            b = d[i + 1]
            i += 2
            if b & 0x80:                            # latch/data
                latch, kind = (b >> 5) & 3, (b >> 4) & 1
                if kind:
                    vol[latch] = b & 0xf
                else:
                    tone[latch] = (tone[latch] & 0x3f0) | (b & 0xf)
            elif kind:                              # data
                vol[latch] = b & 0xf
            else:
                tone[latch] = (tone[latch] & 0xf) | ((b & 0x3f) << 4)
        elif c == 0x61:                             # wait n samples
            i += 3
            frames.append((list(tone), list(vol)))
        elif c in (0x62, 0x63):                     # wait one field
            i += 1
            frames.append((list(tone), list(vol)))
        elif c == 0x66:                             # end
            break
        else:
            i += 1
    return frames


def cost(s):
    """(changes, distinct values, zlib -9 size) of one byte stream."""
    s = bytes(bytearray(s))
    ch = sum(1 for i in range(1, len(s)) if s[i] != s[i - 1])
    return ch, len(set(s)), len(zlib.compress(s, 9))


def row(name, s, frames):
    ch, distinct, z = cost(s)
    print('  %-12s changes %6d (%5.1f%%)  distinct %3d  zlib %6d'
          % (name, ch, 100.0 * ch / frames, distinct, z))
    return z


def main(ym_path, vgm_path):
    frames, clock, rate, regs = read_ym(ym_path)
    print('%s: %d frames, PSG clock %d Hz, replay %d Hz'
          % (ym_path, frames, clock, rate))

    print('\nAY registers - what SongToFap crunches:')
    tone = sum((row(n, regs[r], frames) for n, r in
                (('r0 fine A', 0), ('r2 fine B', 2), ('r4 fine C', 4))))
    tone += row('r1|r3 packed',
                [(regs[3][i] << 4) | regs[1][i] for i in range(frames)], frames)
    tone += row('r5 coarse C', regs[5], frames)
    vol = sum((row(n, regs[r], frames) for n, r in
               (('r8 vol A', 8), ('r9 vol B', 9), ('r10 vol C', 10))))
    mixer = row('r7 mixer', regs[7], frames)
    ay_total = tone + vol + mixer

    f = read_vgm_sn(vgm_path)
    n = len(f)
    print('\nSN76489 - what vgmpacker crunches, after ym2sn.py:')
    sn_tone = 0
    for k in range(3):
        t = [x[0][k] for x in f]
        sn_tone += row('ch%d lo 4' % k, [v & 0xf for v in t], n)
        sn_tone += row('ch%d hi 6' % k, [(v >> 4) & 0x3f for v in t], n)
    sn_noise = row('noise', [x[0][3] for x in f], n)
    sn_vol = sum(row('vol%d' % k, [x[1][k] for x in f], n) for k in range(4))
    sn_total = sn_tone + sn_noise + sn_vol

    print('\n  AY  tone %6d  vol %5d  mixer %5d  = %6d'
          % (tone, vol, mixer, ay_total))
    print('  SN  tone %6d  vol %5d  noise %5d  = %6d'
          % (sn_tone, sn_vol, sn_noise, sn_total))
    print('  the SN log of this tune costs %.2fx the AY log of it'
          % (float(sn_total) / ay_total))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
